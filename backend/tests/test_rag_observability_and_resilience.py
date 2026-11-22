"""Tests for RAG Production Observability, Failure Injection, and Citation Integrity (T260039).

100% CI-safe: runs without ONNX model binaries, external Ollama, or PostgreSQL network dependencies.
"""

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.llm.base import LLMMessage
from app.models.document_chunk import DocumentChunk
from app.models.user import User
from app.services.context_builder import ContextSource, RetrievalContext
from app.services.rag import answer_with_rag
from app.services.rag_observability import (
    RAGObservability,
    get_rag_observability,
    sanitize_correlation_id,
)
from app.services.rag_stream import answer_with_rag_stream
from app.services.reranker import RerankerService, set_reranker_service
from app.services.semantic_search import SemanticSearchResult
from tests.fakes import FakeLLMProvider


def _make_chunk(content: str, *, doc_id=None, idx: int = 0) -> DocumentChunk:
    return DocumentChunk(
        id=uuid4(),
        document_id=doc_id or uuid4(),
        chunk_index=idx,
        content=content,
        char_start=0,
        char_end=len(content),
    )


class _FaultyRerankerService(RerankerService):
    """Deterministic fault-injectable RerankerService for Phase 3 testing."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        delay: float = 0.0,
        timeout_ms: float = 500.0,
        queue_timeout_s: float = 0.5,
        max_concurrency: int = 1,
        max_queue_size: int = 5,
        init_ok: bool = True,
        raise_in_predict: bool = False,
        scores: list[float] | None = None,
    ) -> None:
        settings = Settings(
            reranker_enabled=enabled,
            reranker_max_concurrency=max_concurrency,
            reranker_max_queue_size=max_queue_size,
            reranker_queue_timeout_seconds=queue_timeout_s,
            reranker_timeout_ms=timeout_ms,
            database_url="postgresql+asyncpg://dummy:dummy@localhost/dummy",
            jwt_secret_key="dummy_test_secret_key",
        )
        super().__init__(settings=settings)
        self._init_ok = init_ok
        self._is_ready = init_ok
        self._delay = delay
        self._raise_in_predict = raise_in_predict
        self._scores = scores

    def initialize_model(self) -> bool:
        self.telemetry.record_init(self._init_ok)
        self._is_ready = self._init_ok
        return self._init_ok

    def _sync_predict(self, pairs: list[tuple[str, str]]) -> tuple[list[float], dict[str, float]]:
        if self._delay > 0:
            time.sleep(self._delay)
        if self._raise_in_predict:
            raise RuntimeError("Injected ONNX runtime failure")
        if self._scores is not None and len(self._scores) == len(pairs):
            out = list(self._scores)
        else:
            out = [float(len(pairs) - i) for i in range(len(pairs))]
        return out, {"tokenize_ms": 1.0, "inference_ms": 2.0, "total_ms": 3.0}


@pytest.fixture(autouse=True)
def _reset_singletons():
    get_rag_observability().reset()
    set_reranker_service(None)
    yield
    get_rag_observability().reset()
    set_reranker_service(None)


# -----------------------------------------------------------------------------
# Phase 1: Observability, Correlation ID & Privacy Invariants
# -----------------------------------------------------------------------------
def test_correlation_id_sanitization():
    cid_random = sanitize_correlation_id(None)
    assert len(cid_random) == 12
    assert sanitize_correlation_id("req-123_ABC") == "req-123_ABC"
    # Strips spaces, newlines, injection characters, and bounds to 32 chars
    unsafe = "abc\n[FORGED] " + "x" * 50
    cleaned = sanitize_correlation_id(unsafe)
    assert "\n" not in cleaned
    assert " " not in cleaned
    assert len(cleaned) <= 32


@pytest.mark.anyio
async def test_observability_records_metrics_and_protects_privacy(monkeypatch, caplog):
    doc_id = uuid4()
    secret_query = "SECRET_PROMPT_QUERY_DO_NOT_LOG"
    secret_doc = "CONFIDENTIAL_CHUNK_CONTENT_DO_NOT_LOG"
    c1 = _make_chunk(secret_doc, doc_id=doc_id)

    async def fake_retrieve(*args, **kwargs):
        return RetrievalContext(
            text=f"[Source 1]\n{secret_doc}",
            sources=[
                ContextSource(
                    source_index=1,
                    document_id=doc_id,
                    chunk_id=c1.id,
                    chunk_index=0,
                    content=secret_doc,
                    similarity=0.88,
                    rerank_score=3.21,
                )
            ],
            retrieval_ms=12.5,
            context_assembly_ms=0.4,
            rerank_ms=45.0,
            rerank_used=True,
            rerank_fallback_reason=None,
            retrieval_mode="hybrid",
        )

    import app.services.rag as rag_mod

    monkeypatch.setattr(rag_mod, "retrieve_context", fake_retrieve)
    llm = FakeLLMProvider(response="Verified answer [Source 1].")

    with caplog.at_level(logging.INFO, logger="app.rag.observability"):
        res = await answer_with_rag(
            session=MagicMock(),
            workspace_id=uuid4(),
            query=secret_query,
            llm=llm,
            retrieval_mode="hybrid",
            enable_reranking=True,
        )

    assert "[Source 1]" in res.answer

    # Privacy check: no raw query or chunk content in logs
    log_text = "\n".join(rec.getMessage() for rec in caplog.records)
    assert secret_query not in log_text
    assert secret_doc not in log_text
    assert "mode=hybrid" in log_text
    assert "rerank_used=True" in log_text

    metrics = get_rag_observability().get_metrics()
    assert metrics["requests"]["total"] == 1
    assert metrics["requests"]["success"] == 1
    assert metrics["requests"]["failure_rate"] == 0.0
    assert metrics["requests"]["by_mode"]["hybrid"] == 1
    assert metrics["reranking_degradation"]["degradation_rate"] == 0.0
    assert metrics["latency_ms"]["retrieval_hybrid"]["sample_size"] == 1
    assert metrics["latency_ms"]["retrieval_hybrid"]["p50_ms"] == 12.5
    assert metrics["latency_ms"]["context_assembly"]["p50_ms"] == 0.4


@pytest.mark.anyio
async def test_observability_distinguishes_rerank_degradation_from_rag_failure(monkeypatch):
    doc_id = uuid4()
    c1 = _make_chunk("Authorized chunk content.", doc_id=doc_id)

    async def fake_retrieve(*args, **kwargs):
        return RetrievalContext(
            text="[Source 1]\nAuthorized chunk content.",
            sources=[
                ContextSource(
                    source_index=1,
                    document_id=doc_id,
                    chunk_id=c1.id,
                    chunk_index=0,
                    content="Authorized chunk content.",
                    similarity=0.77,
                    rerank_score=None,
                )
            ],
            retrieval_ms=10.0,
            context_assembly_ms=0.2,
            rerank_ms=51.0,
            rerank_used=False,
            rerank_fallback_reason="inference_timeout",
            retrieval_mode="dense",
        )

    import app.services.rag as rag_mod

    monkeypatch.setattr(rag_mod, "retrieve_context", fake_retrieve)
    llm = FakeLLMProvider(response="Answer from first-stage [Source 1].")

    res = await answer_with_rag(
        session=MagicMock(),
        workspace_id=uuid4(),
        query="test",
        llm=llm,
        retrieval_mode="dense",
        enable_reranking=True,
    )
    assert res.answer == "Answer from first-stage [Source 1]."

    metrics = get_rag_observability().get_metrics()
    assert metrics["requests"]["success"] == 1
    assert metrics["requests"]["failure_rate"] == 0.0
    assert metrics["reranking_degradation"]["opt_in_requests"] == 1
    assert metrics["reranking_degradation"]["degraded_requests"] == 1
    assert metrics["reranking_degradation"]["degradation_rate"] == 1.0


def test_rag_observability_percentile_math():
    obs = RAGObservability(max_samples=100)
    for v in range(1, 101):
        obs.record_request(
            correlation_id=f"c{v}",
            mode="dense",
            stream=False,
            rerank_opt_in=False,
            total_ms=float(v),
        )
    m = obs.get_metrics()["latency_ms"]["total_rag"]
    assert m["sample_size"] == 100
    assert m["p50_ms"] == 50.5
    assert m["p95_ms"] == 95.05
    assert m["p99_ms"] == 99.01


# -----------------------------------------------------------------------------
# Phase 3: Controlled Failure Injection
# -----------------------------------------------------------------------------
@pytest.mark.anyio
async def test_failure_injection_missing_artifact_and_invalid_checksum(tmp_path: Path):
    # 1. Missing model artifact
    missing_svc = RerankerService(
        Settings(
            reranker_enabled=True,
            reranker_model_path=tmp_path / "does_not_exist.onnx",
            database_url="postgresql+asyncpg://dummy:dummy@localhost/dummy",
            jwt_secret_key="dummy",
        )
    )
    c1 = SemanticSearchResult(chunk=_make_chunk("Doc 1"), similarity=0.9)
    res, is_rr, reason = await missing_svc.rerank_candidates(query="q", candidates=[c1], limit=1, opt_in=True)
    assert not is_rr
    assert reason == "model_not_ready"
    assert res[0].chunk.id == c1.chunk.id
    assert missing_svc.telemetry.init_failure_count == 1
    missing_svc.shutdown()

    # 2. Invalid checksum
    fake_model = tmp_path / "corrupt.onnx"
    fake_model.write_bytes(b"corrupt onnx bytes")
    checksum_svc = RerankerService(
        Settings(
            reranker_enabled=True,
            reranker_model_path=fake_model,
            reranker_expected_sha256="0" * 64,
            database_url="postgresql+asyncpg://dummy:dummy@localhost/dummy",
            jwt_secret_key="dummy",
        )
    )
    _, is_rr2, reason2 = await checksum_svc.rerank_candidates(query="q", candidates=[c1], limit=1, opt_in=True)
    assert not is_rr2
    assert reason2 == "model_not_ready"
    assert checksum_svc.telemetry.init_failure_count == 1
    checksum_svc.shutdown()


@pytest.mark.anyio
async def test_failure_injection_db_and_llm_errors_not_hidden_as_rerank_fallback(monkeypatch):
    import app.services.rag as rag_mod

    # 1. Temporary DB unavailability during retrieval
    async def broken_db_retrieve(*args, **kwargs):
        raise ConnectionError("PostgreSQL connection refused")

    monkeypatch.setattr(rag_mod, "retrieve_context", broken_db_retrieve)

    with pytest.raises(ConnectionError, match="PostgreSQL connection refused"):
        await answer_with_rag(
            session=MagicMock(),
            workspace_id=uuid4(),
            query="q",
            llm=FakeLLMProvider(),
            enable_reranking=True,
        )

    m = get_rag_observability().get_metrics()
    assert m["requests"]["failures"] == 1
    assert m["requests"]["failures_by_stage"]["retrieval"] == 1

    # 2. LLM failure must not be hidden
    doc_id = uuid4()
    c1 = _make_chunk("Context", doc_id=doc_id)

    async def ok_retrieve(*args, **kwargs):
        return RetrievalContext(
            text="[Source 1]\nContext",
            sources=[
                ContextSource(
                    source_index=1,
                    document_id=doc_id,
                    chunk_id=c1.id,
                    chunk_index=0,
                    content="Context",
                    similarity=0.8,
                )
            ],
            retrieval_mode="dense",
        )

    monkeypatch.setattr(rag_mod, "retrieve_context", ok_retrieve)

    class BrokenLLM:
        async def generate(self, messages: list[LLMMessage]) -> str:
            raise RuntimeError("Ollama 503 unavailable")

    with pytest.raises(RuntimeError, match="Ollama 503 unavailable"):
        await answer_with_rag(
            session=MagicMock(),
            workspace_id=uuid4(),
            query="q",
            llm=BrokenLLM(),
            enable_reranking=True,
        )

    m2 = get_rag_observability().get_metrics()
    assert m2["requests"]["failures"] == 2
    assert m2["requests"]["failures_by_stage"]["llm_generation"] == 1


@pytest.mark.anyio
async def test_failure_injection_streaming_interruption_and_cancellation(monkeypatch):
    doc_id = uuid4()
    c1 = _make_chunk("Streaming context.", doc_id=doc_id)

    async def ok_retrieve(*args, **kwargs):
        return RetrievalContext(
            text="[Source 1]\nStreaming context.",
            sources=[
                ContextSource(
                    source_index=1,
                    document_id=doc_id,
                    chunk_id=c1.id,
                    chunk_index=0,
                    content="Streaming context.",
                    similarity=0.85,
                    rerank_score=4.5,
                )
            ],
            retrieval_mode="hybrid",
            rerank_used=True,
        )

    import app.services.rag_stream as stream_mod

    monkeypatch.setattr(stream_mod, "retrieve_context", ok_retrieve)

    class InterruptingLLM:
        model = "test-model"

        async def generate_stream(self, messages: list[LLMMessage]) -> AsyncIterator[str]:
            yield "Partial "
            raise RuntimeError("Upstream stream socket reset")

    user = User(id=uuid4(), email="u@test.local")
    events: list[str] = []
    async for ev in answer_with_rag_stream(
        session=None,  # type: ignore[arg-type]
        user=user,
        conversation_id=uuid4(),
        workspace_id=uuid4(),
        query="q",
        llm=InterruptingLLM(),  # type: ignore[arg-type]
        retrieval_mode="hybrid",
        enable_reranking=True,
    ):
        events.append(ev)

    joined = "".join(events)
    assert "event: retrieval_started" in joined
    assert "event: retrieval_completed" in joined
    assert "event: error" in joined
    # T260039: clients get a stable code + understandable message; raw exception text stays in server logs.
    error_payload = json.loads(
        next(ev for ev in events if ev.startswith("event: error")).split("data: ", 1)[1]
    )
    assert error_payload["code"] == "internal_error"
    assert error_payload["stage"] == "llm_generation"
    assert error_payload["error"] == stream_mod.RAG_INTERNAL_ERROR_MESSAGE
    assert "Upstream stream socket reset" not in joined

    m = get_rag_observability().get_metrics()
    assert m["requests"]["failures"] == 1
    assert m["requests"]["failures_by_stage"]["llm_generation"] == 1


@pytest.mark.anyio
async def test_failure_injection_repeated_concurrent_timeouts_no_permit_leak():
    svc = _FaultyRerankerService(
        enabled=True,
        delay=0.12,
        timeout_ms=30.0,
        queue_timeout_s=0.03,
        max_concurrency=1,
        max_queue_size=5,
    )
    c1 = SemanticSearchResult(chunk=_make_chunk("Chunk"), similarity=0.8)

    try:
        results = await asyncio.gather(
            *[svc.rerank_candidates(query=f"q{i}", candidates=[c1], limit=1, opt_in=True) for i in range(4)]
        )
        for res, is_rr, reason in results:
            assert not is_rr
            assert reason in ("inference_timeout", "queue_timeout")
            assert res[0].chunk.id == c1.chunk.id

        # Wait for underlying worker thread to finish
        await asyncio.sleep(0.15)
        metrics = svc.get_metrics()
        assert metrics["active_inferences"] == 0
        assert metrics["fallback_rate"] == 1.0
    finally:
        svc.shutdown()


# -----------------------------------------------------------------------------
# Phase 5: Streaming SSE Ordering, Workspace Isolation & Citation Integrity
# -----------------------------------------------------------------------------
@pytest.mark.anyio
async def test_streaming_sse_order_and_citation_integrity_with_rerank_fallback(monkeypatch):
    import app.services.rag_stream as stream_mod
    import app.services.retrieval as ret_mod

    ws_id = uuid4()
    doc_a = uuid4()
    doc_b = uuid4()
    c_a = _make_chunk("Alpha evidence.", doc_id=doc_a)
    c_b = _make_chunk("Beta evidence.", doc_id=doc_b)

    async def fake_retrieve_candidates(*args, **kwargs):
        # First-stage returns c_a (0.9) then c_b (0.7)
        return [
            SemanticSearchResult(chunk=c_a, similarity=0.9),
            SemanticSearchResult(chunk=c_b, similarity=0.7),
        ]

    async def fake_create_msg(*args, **kwargs):
        return MagicMock(id=uuid4())

    async def fake_save_sources(*args, **kwargs):
        return None

    monkeypatch.setattr(ret_mod, "retrieve_candidates", fake_retrieve_candidates)
    monkeypatch.setattr(stream_mod, "create_conversation_message", fake_create_msg)
    monkeypatch.setattr(stream_mod, "create_workspace_conversation_message", fake_create_msg)
    monkeypatch.setattr(stream_mod, "save_assistant_message_sources", fake_save_sources)

    # Inject faulty reranker that throws during predict -> must fall back to [c_a, c_b]
    faulty_svc = _FaultyRerankerService(enabled=True, raise_in_predict=True)
    set_reranker_service(faulty_svc)

    llm = FakeLLMProvider(stream_chunks=["Based on ", "[Source 1]."])
    user = User(id=uuid4(), email="u@test.local")

    events: list[str] = []
    async for ev in answer_with_rag_stream(
        session=None,  # type: ignore[arg-type]
        user=user,
        conversation_id=uuid4(),
        workspace_id=ws_id,
        query="q",
        llm=llm,
        limit=2,
        retrieval_mode="dense",
        enable_reranking=True,
    ):
        events.append(ev)

    event_names = [line.split("event: ")[1].splitlines()[0] for line in events if line.startswith("event: ")]
    assert event_names == [
        "retrieval_started",
        "retrieval_completed",
        "generation_started",
        "token",
        "token",
        "answer_completed",
    ]
    completed_payload = events[-1]
    assert str(c_a.id) in completed_payload
    assert '"rerank_score": null' in completed_payload
    assert '"similarity": 0.9' in completed_payload

    obs_metrics = get_rag_observability().get_metrics()
    assert obs_metrics["requests"]["success"] == 1
    assert obs_metrics["reranking_degradation"]["degraded_requests"] == 1
