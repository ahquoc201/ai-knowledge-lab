"""Reproducible RAG Production Load Testing & Saturation Benchmark (T260039).

Evaluates:
- A: Dense Retrieval without reranking
- B: Hybrid Retrieval without reranking
- C: Dense Retrieval with opt-in ONNX INT8 reranking
- D: Hybrid Retrieval with opt-in ONNX INT8 reranking
- E: Streaming RAG with Hybrid Retrieval + opt-in ONNX INT8 reranking

Safety Guardrails:
- Strictly targets isolated test DB `ailab_eval_test` on localhost.
- Refuses to run against protected historical `ailab` database or remote hosts.
- Uses locally provisioned ONNX INT8 artifact (never triggers network downloads).
- Uses deterministic mock LLM (`deterministic_mock_llm`) to isolate backend/retrieval/reranker behavior.
"""

import argparse
import asyncio
import json
import os
import resource
import statistics
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.services.rag_stream as rag_stream_mod
from app.core.config import Settings
from app.evaluation.rag_dataset import (
    Answerability,
    RAGDatasetManifest,
    load_rag_dataset,
)
from app.evaluation.real_fixture_provisioner import (
    provision_real_rag_fixtures,
    verify_database_safety,
)
from app.evaluation.reranker_benchmark import generate_distractor_documents
from app.llm.base import LLMMessage
from app.models.user import User
from app.services.rag import answer_with_rag
from app.services.rag_observability import get_rag_observability
from app.services.rag_stream import answer_with_rag_stream
from app.services.reranker import RerankerService, set_reranker_service

REPO_ROOT = Path(__file__).resolve().parents[3]
HOLDOUT_PATH = REPO_ROOT / "backend/datasets/evaluation/rag_quality_dataset_holdout_v1.json"
DEFAULT_DB_URL = "postgresql+asyncpg://ailab:local_only_change_me@/ailab_eval_test?host=/tmp&port=15432"
DEFAULT_MODEL_PATH = REPO_ROOT / "storage/models/reranker/model_int8.onnx"
DEFAULT_REPORT_PATH = REPO_ROOT / "backend/datasets/evaluation/reports/t260039_load_test_report.json"


def _assert_safe_environment(db_url: str) -> None:
    """Enforce strict target-environment safeguards before running load tests."""
    verify_database_safety(db_url)
    parsed = urlparse(db_url)
    db_name = (parsed.path or "").lstrip("/")
    if db_name != "ailab_eval_test":
        raise RuntimeError(f"Load test refused: target DB must be 'ailab_eval_test', got '{db_name}'")
    if parsed.hostname and parsed.hostname not in ("localhost", "127.0.0.1"):
        raise RuntimeError(f"Load test refused: non-local host '{parsed.hostname}'")


class DeterministicMockLLM:
    """Deterministic mock LLM emitting valid [Source 1] citations with minimal fixed overhead."""

    def __init__(self, *, model: str = "deterministic_mock_llm", token_delay_s: float = 0.002) -> None:
        self.model = model
        self.token_delay_s = token_delay_s

    async def generate(self, messages: list[LLMMessage]) -> str:
        await asyncio.sleep(self.token_delay_s * 3)
        return "Câu trả lời tổng hợp từ tài liệu tham chiếu [Source 1]."

    async def generate_stream(self, messages: list[LLMMessage]) -> AsyncIterator[str]:
        for tok in ["Câu ", "trả lời ", "tổng hợp ", "từ tài liệu ", "[Source 1]."]:
            await asyncio.sleep(self.token_delay_s)
            yield tok


def _get_rss_mb() -> float:
    """Return current process RSS memory in MB (Linux /proc/self/status or ru_maxrss fallback)."""
    try:
        with open("/proc/self/status", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    kb = int(line.split()[1])
                    return round(kb / 1024.0, 2)
    except OSError:
        pass
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 2)


def _get_cpu_seconds() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return usage.ru_utime + usage.ru_stime


def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return round(sorted_vals[0], 2)
    idx = (pct / 100.0) * (len(sorted_vals) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = idx - lo
    return round(sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac, 2)


async def _monitor_event_loop_lag(stop_event: asyncio.Event, samples: list[float]) -> None:
    interval = 0.01
    while not stop_event.is_set():
        t0 = time.perf_counter()
        await asyncio.sleep(interval)
        lag_ms = max(0.0, (time.perf_counter() - t0 - interval) * 1000.0)
        samples.append(lag_ms)


async def _run_profile_concurrency(
    *,
    profile_name: str,
    mode: str,
    enable_reranking: bool,
    streaming: bool,
    concurrency: int,
    total_requests: int,
    queries: list[str],
    session_factory: Any,
    workspace_id: Any,
    reranker_service: RerankerService,
) -> dict[str, Any]:
    obs = get_rag_observability()
    obs.reset()
    reranker_service.telemetry.reset()

    llm = DeterministicMockLLM()
    dummy_user = User(id=uuid4(), email="loadtest@local.test")

    latencies_ms: list[float] = []
    ttft_list_ms: list[float] = []
    errors = 0
    lag_samples: list[float] = []

    stop_lag = asyncio.Event()
    lag_task = asyncio.create_task(_monitor_event_loop_lag(stop_lag, lag_samples))

    sem = asyncio.Semaphore(concurrency)
    rss_before = _get_rss_mb()
    rss_peak = rss_before
    cpu_before = _get_cpu_seconds()
    wall_start = time.perf_counter()

    async def _execute_one(idx: int) -> None:
        nonlocal errors, rss_peak
        query = queries[idx % len(queries)]
        async with sem:
            t0 = time.perf_counter()
            try:
                async with session_factory() as session:
                    if streaming:
                        ttft: float | None = None
                        async for event_str in answer_with_rag_stream(
                            session=session,
                            user=dummy_user,
                            conversation_id=uuid4(),
                            workspace_id=workspace_id,
                            query=query,
                            llm=llm,
                            limit=5,
                            retrieval_mode=mode,
                            enable_reranking=enable_reranking,
                        ):
                            if "event: token" in event_str and ttft is None:
                                ttft = (time.perf_counter() - t0) * 1000.0
                        if ttft is not None:
                            ttft_list_ms.append(ttft)
                    else:
                        await answer_with_rag(
                            session=session,
                            user_id=dummy_user.id,
                            workspace_id=workspace_id,
                            query=query,
                            llm=llm,
                            limit=5,
                            retrieval_mode=mode,
                            enable_reranking=enable_reranking,
                        )
                latencies_ms.append((time.perf_counter() - t0) * 1000.0)
            except Exception:  # noqa: BLE001
                errors += 1
            finally:
                rss_now = _get_rss_mb()
                rss_peak = max(rss_peak, rss_now)

    await asyncio.gather(*[_execute_one(i) for i in range(total_requests)])

    wall_elapsed_s = max(0.001, time.perf_counter() - wall_start)
    cpu_elapsed_s = max(0.0, _get_cpu_seconds() - cpu_before)
    stop_lag.set()
    await lag_task

    rss_after = _get_rss_mb()
    sorted_lats = sorted(latencies_ms)
    sorted_ttft = sorted(ttft_list_ms)
    sorted_lag = sorted(lag_samples)

    rr_metrics = reranker_service.get_metrics()
    obs_metrics = obs.get_metrics()

    return {
        "profile": profile_name,
        "mode": mode,
        "enable_reranking": enable_reranking,
        "streaming": streaming,
        "concurrency": concurrency,
        "total_requests": total_requests,
        "completed_requests": len(latencies_ms),
        "errors": errors,
        "throughput_rps": round(len(latencies_ms) / wall_elapsed_s, 2),
        "wall_time_s": round(wall_elapsed_s, 3),
        "latency_ms": {
            "sample_size": len(sorted_lats),
            "mean": round(statistics.mean(sorted_lats), 2) if sorted_lats else 0.0,
            "p50": _percentile(sorted_lats, 50.0),
            "p95": _percentile(sorted_lats, 95.0),
            "p99": _percentile(sorted_lats, 99.0),
        },
        "streaming_ttft_ms": {
            "sample_size": len(sorted_ttft),
            "p50": _percentile(sorted_ttft, 50.0),
            "p95": _percentile(sorted_ttft, 95.0),
        }
        if streaming
        else None,
        "reranker_metrics": {
            "total_opt_in": rr_metrics["total_opt_in"],
            "total_success": rr_metrics["total_success"],
            "total_fallback": rr_metrics["total_fallback"],
            "fallback_rate": rr_metrics["fallback_rate"],
            "fallback_reasons": rr_metrics["fallback_reasons"],
            "queue_timeouts": rr_metrics["queue_timeouts"],
            "inference_timeouts": rr_metrics["inference_timeouts"],
            "capacity_rejections": rr_metrics["capacity_rejections"],
            "p50_queue_wait_ms": rr_metrics["p50_queue_wait_ms"],
            "p50_inference_ms": rr_metrics["p50_inference_ms"],
            "p95_inference_ms": rr_metrics["p95_inference_ms"],
        },
        "pipeline_breakdown_ms": {
            "retrieval_p50": obs_metrics["latency_ms"]["retrieval_all"]["p50_ms"],
            "context_p50": obs_metrics["latency_ms"]["context_assembly"]["p50_ms"],
            "llm_p50": obs_metrics["latency_ms"]["llm_generation"]["p50_ms"],
        },
        "resources": {
            "cpu_seconds": round(cpu_elapsed_s, 3),
            "cpu_utilization_pct": round((cpu_elapsed_s / wall_elapsed_s) * 100.0, 1),
            "rss_before_mb": rss_before,
            "rss_after_mb": rss_after,
            "rss_peak_mb": rss_peak,
            "event_loop_lag_p50_ms": _percentile(sorted_lag, 50.0),
            "event_loop_lag_max_ms": round(max(sorted_lag), 2) if sorted_lag else 0.0,
        },
    }


async def run_load_test(
    *,
    db_url: str = DEFAULT_DB_URL,
    model_path: Path = DEFAULT_MODEL_PATH,
    concurrencies: list[int] | None = None,
    requests_per_level: int = 12,
    report_path: Path = DEFAULT_REPORT_PATH,
) -> dict[str, Any]:
    _assert_safe_environment(db_url)
    if not model_path.is_file():
        raise FileNotFoundError(f"ONNX INT8 model missing at {model_path}")

    concurrencies = concurrencies or [1, 2, 5, 10]
    engine = create_async_engine(db_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    holdout_manifest = load_rag_dataset(HOLDOUT_PATH)
    distractors = generate_distractor_documents(60)
    augmented_manifest = RAGDatasetManifest(
        dataset_id="ai-knowledge-lab-rag-quality-holdout-augmented",
        version="1.0",
        description="Holdout dataset augmented with 60 realistic technical distractors",
        documents=list(holdout_manifest.documents) + distractors,
        cases=holdout_manifest.cases,
    )
    answerable_queries = [
        c.query for c in holdout_manifest.cases if c.expected_answerability == Answerability.ANSWERABLE
    ]

    settings = Settings(
        reranker_enabled=True,
        reranker_model_path=model_path,
        reranker_max_concurrency=1,
        reranker_max_queue_size=5,
        reranker_queue_timeout_seconds=2.0,
        reranker_intra_op_threads=4,
        reranker_timeout_ms=3000.0,
        database_url=db_url,
    )
    reranker_service = RerankerService(settings=settings)
    if not reranker_service.initialize_model():
        raise RuntimeError("Failed to initialize ONNX INT8 reranker model")
    set_reranker_service(reranker_service)

    # Avoid external Ollama discovery calls during deterministic mock-LLM streaming load tests
    class _StubRouter:
        async def select_model(self, **kwargs: Any) -> Any:
            return type(
                "_Decision",
                (),
                {
                    "selected_model": "deterministic_mock_llm",
                    "task_type": "rag",
                    "selection_reason": "load_test_stub",
                    "is_fallback": False,
                },
            )()

    orig_router = rag_stream_mod.ModelRouter
    rag_stream_mod.ModelRouter = _StubRouter  # type: ignore[misc]

    results: list[dict[str, Any]] = []
    profiles = [
        ("A_dense_no_rerank", "dense", False, False),
        ("B_hybrid_no_rerank", "hybrid", False, False),
        ("C_dense_rerank", "dense", True, False),
        ("D_hybrid_rerank", "hybrid", True, False),
        ("E_streaming_hybrid_rerank", "hybrid", True, True),
    ]

    try:
        async with provision_real_rag_fixtures(
            engine=engine, manifest=augmented_manifest, allow_fixture_writes=True
        ) as env:
            # All holdout queries target ws_alpha or ws_beta; pick primary workspace
            target_ws_id = next(iter(env.workspace_map.values()))

            # Warm-up 1 pass
            await _run_profile_concurrency(
                profile_name="warmup",
                mode="hybrid",
                enable_reranking=True,
                streaming=False,
                concurrency=1,
                total_requests=2,
                queries=answerable_queries,
                session_factory=session_factory,
                workspace_id=target_ws_id,
                reranker_service=reranker_service,
            )

            for profile_name, mode, use_rr, is_stream in profiles:
                for conc in concurrencies:
                    res = await _run_profile_concurrency(
                        profile_name=profile_name,
                        mode=mode,
                        enable_reranking=use_rr,
                        streaming=is_stream,
                        concurrency=conc,
                        total_requests=requests_per_level,
                        queries=answerable_queries,
                        session_factory=session_factory,
                        workspace_id=target_ws_id,
                        reranker_service=reranker_service,
                    )
                    results.append(res)
                    print(
                        f"[{profile_name} | c={conc}] rps={res['throughput_rps']} "
                        f"p50={res['latency_ms']['p50']}ms p95={res['latency_ms']['p95']}ms "
                        f"p99={res['latency_ms']['p99']}ms (n={res['latency_ms']['sample_size']}) "
                        f"fallback={res['reranker_metrics']['total_fallback']} "
                        f"rss={res['resources']['rss_peak_mb']}MB lag_p50={res['resources']['event_loop_lag_p50_ms']}ms"
                    )
    finally:
        rag_stream_mod.ModelRouter = orig_router  # type: ignore[misc]
        reranker_service.shutdown()
        await engine.dispose()

    report = {
        "metadata": {
            "task_id": "T260039",
            "llm_mode": "deterministic_mock_llm",
            "corpus": "augmented_74_chunks",
            "requests_per_level": requests_per_level,
            "concurrencies": concurrencies,
            "cpu_cores_logical": os.cpu_count(),
            "reranker_config": {
                "max_concurrency": settings.reranker_max_concurrency,
                "max_queue_size": settings.reranker_max_queue_size,
                "queue_timeout_seconds": settings.reranker_queue_timeout_seconds,
                "intra_op_threads": settings.reranker_intra_op_threads,
                "timeout_ms": settings.reranker_timeout_ms,
                "pool_size": settings.reranker_pool_size,
            },
        },
        "results": results,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="T260039 RAG Production Load Test")
    parser.add_argument("--requests", type=int, default=12, help="Requests per concurrency level")
    parser.add_argument("--concurrencies", type=str, default="1,2,5,10", help="Comma-separated concurrency levels")
    args = parser.parse_args()

    concurrencies = [int(x.strip()) for x in args.concurrencies.split(",") if x.strip()]
    asyncio.run(run_load_test(concurrencies=concurrencies, requests_per_level=args.requests))


if __name__ == "__main__":
    main()
