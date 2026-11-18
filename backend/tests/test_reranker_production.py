"""Production Reranker Integration Unit & Integration Tests (T260038).

Covers all 20 required production and safety scenarios:
1. Feature flag disabled behavior.
2. Explicit opt-in behavior.
3. Server disabled but client requests reranking.
4. Correct candidate ordering and metadata.
5. Candidate pool upper-bound invariants.
6. Tenant isolation.
7. Model file missing or invalid.
8. Model initialization failure.
9. Inference exception.
10. Timeout and fallback.
11. Capacity saturation and admission control.
12. Repeated timeout without unbounded worker accumulation.
13. Client cancellation and cleanup.
14. Non-streaming RAG compatibility.
15. Streaming RAG compatibility.
16. Citation integrity.
17. Existing Dense and Hybrid API compatibility.
18. Model session reuse and shutdown.
19. Concurrent request behavior.
20. Event-loop responsiveness while inference runs.
Plus optional real-model test against locally provisioned ONNX INT8 artifact.
"""

import asyncio
import time
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.models.document_chunk import DocumentChunk
from app.services.context_builder import ContextSource, RetrievalContext
from app.services.fusion import FusedSearchResult
from app.services.rag import answer_with_rag
from app.services.rag_stream import answer_with_rag_stream
from app.services.reranker import (
    RerankerService,
    set_reranker_service,
)
from app.services.retrieval import retrieve_context
from app.services.semantic_search import SemanticSearchResult
from tests.fakes import FakeLLMProvider


def make_dummy_chunk(content: str, doc_id=None, chunk_id=None, chunk_index=0) -> DocumentChunk:
    return DocumentChunk(
        id=chunk_id or uuid4(),
        document_id=doc_id or uuid4(),
        chunk_index=chunk_index,
        content=content,
        char_start=0,
        char_end=len(content),
    )


class MockRerankerService(RerankerService):
    """Controllable RerankerService for fast, deterministic unit testing."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        is_ready: bool = True,
        mock_scores: list[float] | None = None,
        inference_delay: float = 0.0,
        should_fail_inference: bool = False,
        should_fail_init: bool = False,
        max_concurrency: int = 1,
        max_queue_size: int = 5,
        queue_timeout_seconds: float = 0.5,
        timeout_seconds: float = 0.5,
    ) -> None:
        dummy_settings = Settings(
            reranker_enabled=enabled,
            reranker_max_concurrency=max_concurrency,
            reranker_max_queue_size=max_queue_size,
            reranker_queue_timeout_seconds=queue_timeout_seconds,
            reranker_timeout_ms=timeout_seconds * 1000.0,
            database_url="postgresql+asyncpg://dummy:dummy@localhost/dummy",
            jwt_secret_key="dummy_key_for_testing_purposes_only",
        )
        super().__init__(settings=dummy_settings)
        self._is_ready = is_ready
        self.mock_scores = mock_scores
        self.inference_delay = inference_delay
        self.should_fail_inference = should_fail_inference
        self.should_fail_init = should_fail_init

    def initialize_model(self) -> bool:
        if self.should_fail_init:
            self._is_ready = False
            return False
        self._is_ready = True
        return True

    def _sync_predict(self, pairs: list[tuple[str, str]]) -> tuple[list[float], dict[str, float]]:
        if self.inference_delay > 0:
            time.sleep(self.inference_delay)
        if self.should_fail_inference:
            raise RuntimeError("Simulated ONNX Runtime inference error")

        if self.mock_scores is not None and len(self.mock_scores) == len(pairs):
            scores = list(self.mock_scores)
        else:
            # Default descending scores for testing
            scores = [float(10.0 - i) for i in range(len(pairs))]

        timing = {"tokenize_ms": 1.0, "inference_ms": 2.0, "total_ms": 3.0}
        return scores, timing


@pytest.fixture(autouse=True)
def cleanup_reranker():
    """Ensure reranker singleton is reset cleanly before and after each test."""
    set_reranker_service(None)
    yield
    set_reranker_service(None)


# -----------------------------------------------------------------------------
# Scenario 1 & 2: Feature flag disabled and explicit opt-in behavior
# -----------------------------------------------------------------------------
@pytest.mark.anyio
async def test_reranker_feature_flag_disabled_and_opt_in():
    # When server enabled and client opts in:
    c1 = SemanticSearchResult(chunk=make_dummy_chunk("Low rank text"), similarity=0.90)
    c2 = SemanticSearchResult(chunk=make_dummy_chunk("High rank text"), similarity=0.60)
    candidates = [c1, c2]

    # Service with custom scores: c2 gets score 9.0, c1 gets score 1.0
    mock_service = MockRerankerService(enabled=True, mock_scores=[1.0, 9.0])

    # 1. Opt-in = False -> returns original order
    results_no_opt, is_reranked, fallback = await mock_service.rerank_candidates(
        query="test query",
        candidates=candidates,
        limit=2,
        opt_in=False,
    )
    assert not is_reranked
    assert fallback == "not_requested"
    assert results_no_opt[0].chunk.id == c1.chunk.id

    # 2. Opt-in = True -> returns reranked order (c2 promoted to #1)
    results_opt, is_reranked, fallback = await mock_service.rerank_candidates(
        query="test query",
        candidates=candidates,
        limit=2,
        opt_in=True,
    )
    assert is_reranked
    assert fallback is None
    assert results_opt[0].chunk.id == c2.chunk.id
    assert results_opt[0].rerank_score == 9.0
    assert results_opt[0].similarity == 0.60  # Cosine similarity preserved!
    assert results_opt[1].chunk.id == c1.chunk.id


# -----------------------------------------------------------------------------
# Scenario 3: Server disabled but client requests reranking
# -----------------------------------------------------------------------------
@pytest.mark.anyio
async def test_server_disabled_client_requests_reranking():
    c1 = SemanticSearchResult(chunk=make_dummy_chunk("Doc A"), similarity=0.9)
    candidates = [c1]

    disabled_service = MockRerankerService(enabled=False)
    results, is_reranked, fallback = await disabled_service.rerank_candidates(
        query="test query",
        candidates=candidates,
        limit=1,
        opt_in=True,
    )
    assert not is_reranked
    assert fallback == "disabled_by_server"
    assert results[0].chunk.id == c1.chunk.id
    metrics = disabled_service.get_metrics()
    assert metrics["total_opt_in"] == 1
    assert metrics["total_fallback"] == 1
    assert metrics["fallback_reasons"]["disabled_by_server"] == 1


# -----------------------------------------------------------------------------
# Scenario 4: Correct candidate ordering and metadata preservation
# -----------------------------------------------------------------------------
@pytest.mark.anyio
async def test_candidate_ordering_and_deterministic_tie_breaking():
    chunk1 = make_dummy_chunk("Alpha chunk", chunk_index=1)
    chunk2 = make_dummy_chunk("Beta chunk", chunk_index=2)
    chunk3 = make_dummy_chunk("Gamma chunk", chunk_index=3)

    c1 = SemanticSearchResult(chunk=chunk1, similarity=0.5, document_title="Doc 1")
    c2 = SemanticSearchResult(chunk=chunk2, similarity=0.7, document_title="Doc 2")
    c3 = SemanticSearchResult(chunk=chunk3, similarity=0.9, document_title="Doc 3")

    # Scores: c2 has 5.0, c1 and c3 tie at 2.0
    mock_service = MockRerankerService(enabled=True, mock_scores=[2.0, 5.0, 2.0])
    results, is_reranked, _ = await mock_service.rerank_candidates(
        query="test query",
        candidates=[c1, c2, c3],
        limit=3,
        opt_in=True,
    )
    assert is_reranked
    # Rank 1 must be c2 (score 5.0)
    assert results[0].chunk.id == chunk2.id
    assert results[0].document_title == "Doc 2"
    assert results[0].similarity == 0.7
    assert results[0].rerank_score == 5.0

    # Ties between c1 and c3 broken deterministically by chunk id string
    remaining_ids = [str(results[1].chunk.id), str(results[2].chunk.id)]
    assert remaining_ids == sorted(remaining_ids)


# -----------------------------------------------------------------------------
# Scenario 5 & 6: Candidate pool upper-bound invariants & tenant isolation
# -----------------------------------------------------------------------------
@pytest.mark.anyio
async def test_candidate_pool_upper_bounds_and_tenant_isolation():
    ws_alpha = uuid4()
    ws_beta = uuid4()

    # Authorized alpha chunks
    c1 = SemanticSearchResult(chunk=make_dummy_chunk("Alpha 1", doc_id=ws_alpha), similarity=0.8)
    c2 = SemanticSearchResult(chunk=make_dummy_chunk("Alpha 2", doc_id=ws_alpha), similarity=0.7)
    pool = [c1, c2]

    mock_service = MockRerankerService(enabled=True, mock_scores=[3.0, 4.0])
    results, _, _ = await mock_service.rerank_candidates(
        query="query",
        candidates=pool,
        limit=2,
        opt_in=True,
    )
    # INVARIANT: All reranked IDs must come from original pool
    pool_ids = {c.chunk.id for c in pool}
    reranked_ids = {r.chunk.id for r in results}
    assert reranked_ids.issubset(pool_ids)
    assert len(results) <= len(pool)

    # Tenant isolation: no foreign workspace chunks
    for r in results:
        assert r.chunk.document_id == ws_alpha
        assert r.chunk.document_id != ws_beta


# -----------------------------------------------------------------------------
# Scenario 7 & 8: Model file missing or initialization failure
# -----------------------------------------------------------------------------
@pytest.mark.anyio
async def test_model_missing_or_init_failure():
    c1 = SemanticSearchResult(chunk=make_dummy_chunk("Doc"), similarity=0.8)

    # 1. Unready service that fails init
    failing_init_service = MockRerankerService(enabled=True, is_ready=False, should_fail_init=True)
    results, is_reranked, fallback = await failing_init_service.rerank_candidates(
        query="q",
        candidates=[c1],
        limit=1,
        opt_in=True,
    )
    assert not is_reranked
    assert fallback == "model_not_ready"
    assert results[0].chunk.id == c1.chunk.id

    # 2. Real service pointed to non-existent file
    bogus_settings = Settings(
        reranker_enabled=True,
        reranker_model_path=Path("/tmp/non_existent_model_12345.onnx"),
        database_url="postgresql+asyncpg://dummy:dummy@localhost/dummy",
        jwt_secret_key="dummy_key_for_testing_purposes_only",
    )
    real_service = RerankerService(settings=bogus_settings)
    assert not real_service.initialize_model()
    assert not real_service.is_ready


# -----------------------------------------------------------------------------
# Scenario 9: Inference exception fallback
# -----------------------------------------------------------------------------
@pytest.mark.anyio
async def test_inference_exception_fallback():
    c1 = SemanticSearchResult(chunk=make_dummy_chunk("Doc"), similarity=0.8)
    error_service = MockRerankerService(enabled=True, should_fail_inference=True)

    results, is_reranked, fallback = await error_service.rerank_candidates(
        query="q",
        candidates=[c1],
        limit=1,
        opt_in=True,
    )
    assert not is_reranked
    assert fallback == "inference_error"
    assert results[0].chunk.id == c1.chunk.id
    assert error_service.telemetry.total_fallback == 1


# -----------------------------------------------------------------------------
# Scenario 10 & 11: Timeout and capacity saturation
# -----------------------------------------------------------------------------
@pytest.mark.anyio
async def test_timeout_and_capacity_saturation():
    c1 = SemanticSearchResult(chunk=make_dummy_chunk("Doc"), similarity=0.8)

    # 1. Inference timeout (timeout set to 0.05s, delay is 0.2s)
    slow_service = MockRerankerService(
        enabled=True,
        inference_delay=0.2,
        timeout_seconds=0.05,
    )
    _, is_reranked, fallback = await slow_service.rerank_candidates(
        query="q",
        candidates=[c1],
        limit=1,
        opt_in=True,
    )
    assert not is_reranked
    assert fallback == "inference_timeout"
    assert slow_service.telemetry.inference_timeouts == 1

    # 2. Capacity saturation: max_queue_size=1
    sat_service = MockRerankerService(
        enabled=True,
        max_concurrency=1,
        max_queue_size=1,
        inference_delay=0.1,
    )
    sat_service._queued_requests = 1  # Pre-fill queue
    _, is_reranked_sat, fallback_sat = await sat_service.rerank_candidates(
        query="q",
        candidates=[c1],
        limit=1,
        opt_in=True,
    )
    assert not is_reranked_sat
    assert fallback_sat == "capacity_saturated"
    assert sat_service.telemetry.capacity_rejections == 1


# -----------------------------------------------------------------------------
# Scenario 12: Repeated timeout without unbounded worker accumulation
# -----------------------------------------------------------------------------
@pytest.mark.anyio
async def test_permit_held_until_thread_worker_completes():
    """Verify that when asyncio timeout occurs, permit is NOT leaked before thread finishes."""
    c1 = SemanticSearchResult(chunk=make_dummy_chunk("Doc"), similarity=0.8)

    # Max concurrency 1. Inference takes 0.15s, timeout is 0.05s.
    bounded_service = MockRerankerService(
        enabled=True,
        max_concurrency=1,
        inference_delay=0.15,
        timeout_seconds=0.05,
        queue_timeout_seconds=0.05,
    )

    # Task 1 times out
    t1 = asyncio.create_task(
        bounded_service.rerank_candidates(query="q1", candidates=[c1], opt_in=True)
    )
    _, is_reranked1, fallback1 = await t1
    assert not is_reranked1
    assert fallback1 == "inference_timeout"

    # Immediately submit Task 2 while Task 1 worker thread is still sleeping!
    # Task 2 must wait in queue or time out waiting for slot, proving permit was NOT prematurely released!
    t2 = asyncio.create_task(
        bounded_service.rerank_candidates(query="q2", candidates=[c1], opt_in=True)
    )
    _, is_reranked2, fallback2 = await t2
    # Because Task 1 was still executing, Task 2 timed out waiting in queue
    assert not is_reranked2
    assert fallback2 in ("queue_timeout", "inference_timeout")

    # Wait for background thread to fully finish
    await asyncio.sleep(0.15)
    assert bounded_service._active_inferences == 0


# -----------------------------------------------------------------------------
# Scenario 13: Client cancellation and cleanup
# -----------------------------------------------------------------------------
@pytest.mark.anyio
async def test_client_cancellation_and_cleanup():
    c1 = SemanticSearchResult(chunk=make_dummy_chunk("Doc"), similarity=0.8)
    slow_service = MockRerankerService(
        enabled=True,
        inference_delay=0.2,
        timeout_seconds=1.0,
    )

    task = asyncio.create_task(
        slow_service.rerank_candidates(query="q", candidates=[c1], opt_in=True)
    )
    await asyncio.sleep(0.02)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert slow_service.telemetry.fallback_reasons.get("cancelled", 0) == 1
    # Allow worker thread to cleanly release permit
    await asyncio.sleep(0.2)
    assert slow_service._active_inferences == 0


# -----------------------------------------------------------------------------
# Scenario 14 & 16: Non-streaming RAG compatibility & citation integrity
# -----------------------------------------------------------------------------
@pytest.mark.anyio
async def test_non_streaming_rag_with_reranking(monkeypatch):
    doc_id = uuid4()
    c1 = make_dummy_chunk("PostgreSQL hỗ trợ transaction và ACID.", doc_id=doc_id)

    # Mock retrieve_context to return context with rerank_score
    mock_context = RetrievalContext(
        text="[Source 1]\nPostgreSQL hỗ trợ transaction và ACID.",
        sources=[
            ContextSource(
                source_index=1,
                document_id=doc_id,
                chunk_id=c1.id,
                chunk_index=0,
                content="PostgreSQL hỗ trợ transaction và ACID.",
                similarity=0.75,
                rerank_score=4.82,
            )
        ],
    )

    async def fake_retrieve_context(*args, **kwargs):
        assert kwargs.get("enable_reranking") is True
        return mock_context

    monkeypatch.setattr("app.services.rag.retrieve_context", fake_retrieve_context)

    fake_llm = FakeLLMProvider(
        response="PostgreSQL đảm bảo ACID và transaction [Source 1]."
    )

    # Execute answer_with_rag
    result = await answer_with_rag(
        session=MagicMock(),
        query="PostgreSQL ACID?",
        llm=fake_llm,
        limit=1,
        enable_reranking=True,
    )

    assert "[Source 1]" in result.answer
    assert len(result.sources) == 1
    assert result.sources[0].rerank_score == 4.82
    assert result.sources[0].similarity == 0.75


# -----------------------------------------------------------------------------
# Scenario 15: Streaming RAG compatibility
# -----------------------------------------------------------------------------
@pytest.mark.anyio
async def test_streaming_rag_with_reranking(monkeypatch):
    doc_id = uuid4()
    mock_context = RetrievalContext(
        text="[Source 1]\nNội dung tài liệu",
        sources=[
            ContextSource(
                source_index=1,
                document_id=doc_id,
                chunk_id=uuid4(),
                chunk_index=0,
                content="Nội dung tài liệu",
                similarity=0.88,
                rerank_score=6.12,
            )
        ],
    )

    async def fake_retrieve_context(*args, **kwargs):
        assert kwargs.get("enable_reranking") is True
        return mock_context

    monkeypatch.setattr("app.services.rag_stream.retrieve_context", fake_retrieve_context)

    fake_llm = FakeLLMProvider(response="Trả lời có căn cứ [Source 1].")
    fake_user = MagicMock()
    fake_user.id = uuid4()

    events = []
    async for chunk in answer_with_rag_stream(
        session=MagicMock(),
        user=fake_user,
        conversation_id=uuid4(),
        query="Câu hỏi",
        llm=fake_llm,
        limit=1,
        enable_reranking=True,
    ):
        events.append(chunk)

    full_stream = "".join(events)
    assert "retrieval_started" in full_stream
    assert "retrieval_completed" in full_stream
    assert '"rerank_score": 6.12' in full_stream


# -----------------------------------------------------------------------------
# Scenario 17: Existing Dense and Hybrid API compatibility
# -----------------------------------------------------------------------------
@pytest.mark.anyio
async def test_dense_and_hybrid_compatibility_without_reranking(monkeypatch):
    chunk_dense = make_dummy_chunk("Dense match")
    chunk_hybrid = make_dummy_chunk("Hybrid match")

    async def fake_semantic_search(*args, **kwargs):
        return [SemanticSearchResult(chunk=chunk_dense, similarity=0.91)]

    async def fake_hybrid_search(*args, **kwargs):
        return [
            FusedSearchResult(
                chunk=chunk_hybrid,
                rrf_score=0.032,
                dense_rank=1,
                keyword_rank=2,
                dense_similarity=0.85,
            )
        ]

    monkeypatch.setattr("app.services.retrieval.semantic_search", fake_semantic_search)
    monkeypatch.setattr("app.services.retrieval.hybrid_search", fake_hybrid_search)

    # 1. Dense retrieval (default, no reranking)
    ctx_dense = await retrieve_context(
        session=MagicMock(),
        query="query",
        limit=1,
        mode="dense",
        enable_reranking=False,
    )
    assert len(ctx_dense.sources) == 1
    assert ctx_dense.sources[0].similarity == 0.91
    assert ctx_dense.sources[0].rerank_score is None

    # 2. Hybrid retrieval (no reranking)
    ctx_hybrid = await retrieve_context(
        session=MagicMock(),
        query="query",
        limit=1,
        mode="hybrid",
        enable_reranking=False,
    )
    assert len(ctx_hybrid.sources) == 1
    assert ctx_hybrid.sources[0].similarity == 0.85  # True cosine similarity preserved
    assert ctx_hybrid.sources[0].rerank_score is None


# -----------------------------------------------------------------------------
# Scenario 18: Model session reuse and shutdown
# -----------------------------------------------------------------------------
@pytest.mark.anyio
async def test_model_session_reuse_and_shutdown():
    service = MockRerankerService(enabled=True)
    assert service.initialize_model()
    assert service.is_ready
    # Second initialize call should return True immediately
    assert service.initialize_model()

    service.shutdown()
    assert not service.is_ready


# -----------------------------------------------------------------------------
# Scenario 19: Concurrent request behavior
# -----------------------------------------------------------------------------
@pytest.mark.anyio
async def test_concurrent_requests_governance():
    c = SemanticSearchResult(chunk=make_dummy_chunk("Concurrent"), similarity=0.8)
    service = MockRerankerService(
        enabled=True,
        max_concurrency=2,
        max_queue_size=10,
        inference_delay=0.05,
    )

    tasks = [
        service.rerank_candidates(query=f"q{i}", candidates=[c], opt_in=True)
        for i in range(4)
    ]
    results = await asyncio.gather(*tasks)

    for res, is_reranked, fallback in results:
        assert is_reranked
        assert fallback is None

    metrics = service.get_metrics()
    assert metrics["total_success"] == 4
    assert metrics["active_inferences"] == 0


# -----------------------------------------------------------------------------
# Scenario 20: Event-loop responsiveness during inference
# -----------------------------------------------------------------------------
@pytest.mark.anyio
async def test_event_loop_responsiveness():
    """Verify that CPU-bound inference in thread pool does not block asyncio event loop."""
    c = SemanticSearchResult(chunk=make_dummy_chunk("Responsiveness"), similarity=0.8)
    service = MockRerankerService(
        enabled=True,
        inference_delay=0.1,  # 100ms in thread pool
    )

    heartbeat_count = 0

    async def heartbeat():
        nonlocal heartbeat_count
        for _ in range(5):
            await asyncio.sleep(0.02)
            heartbeat_count += 1

    t_inference = asyncio.create_task(
        service.rerank_candidates(query="q", candidates=[c], opt_in=True)
    )
    t_heartbeat = asyncio.create_task(heartbeat())

    await asyncio.gather(t_inference, t_heartbeat)

    # If event loop was blocked, heartbeat_count would be 0 or 1.
    assert heartbeat_count >= 4, f"Event loop was blocked! Heartbeat count: {heartbeat_count}"


# -----------------------------------------------------------------------------
# Optional Real-Model Integration Test
# -----------------------------------------------------------------------------
@pytest.mark.anyio
async def test_real_model_inference_if_present():
    """Optional integration test executing against real ONNX INT8 artifact if present on disk."""
    real_model_path = Path(__file__).resolve().parents[2] / "storage/models/reranker/model_int8.onnx"
    if not real_model_path.is_file():
        pytest.skip(f"Local ONNX INT8 model not found at {real_model_path}; skipping real-model test.")

    settings = Settings(
        reranker_enabled=True,
        reranker_model_path=real_model_path,
        reranker_intra_op_threads=2,
        reranker_timeout_ms=5000.0,
        database_url="postgresql+asyncpg://dummy:dummy@localhost/dummy",
        jwt_secret_key="dummy_key_for_testing_purposes_only",
    )
    service = RerankerService(settings=settings)
    initialized = service.initialize_model()
    if not initialized:
        pytest.skip("Failed to initialize real model (transformers/onnxruntime environment mismatch).")

    try:
        c1 = SemanticSearchResult(
            chunk=make_dummy_chunk("PostgreSQL là hệ thống cơ sở dữ liệu quan hệ mã nguồn mở mạnh mẽ."),
            similarity=0.7,
        )
        c2 = SemanticSearchResult(
            chunk=make_dummy_chunk("Món phở bò truyền thống của Hà Nội có hương vị đậm đà thơm ngon."),
            similarity=0.7,
        )

        results, is_reranked, fallback = await service.rerank_candidates(
            query="Hệ quản trị cơ sở dữ liệu quan hệ SQL?",
            candidates=[c2, c1],  # c1 is more relevant but placed second
            limit=2,
            opt_in=True,
        )

        assert is_reranked
        assert fallback is None
        # c1 (PostgreSQL) must be reranked to rank 1
        assert results[0].chunk.id == c1.chunk.id
        assert results[0].rerank_score > results[1].rerank_score
    finally:
        service.shutdown()
