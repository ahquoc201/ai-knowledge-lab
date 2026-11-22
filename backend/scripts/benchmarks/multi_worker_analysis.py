"""Phase 4: Multi-Worker Resource & Contention Analysis for ONNX INT8 Reranker (T260039).

Spawns 1 vs 2 isolated Python worker processes (simulating Uvicorn workers, each with
its own ONNX InferenceSession, ThreadPoolExecutor, and Semaphore) to measure:
- Isolated per-worker steady-state & peak RSS memory footprint
- CPU contention (12 logical threads = 6 physical cores with Hyper-Threading, not 12 dedicated cores)
- Aggregate throughput and P50/P95 latency under concurrent load
"""

import argparse
import asyncio
import json
import multiprocessing
import os
import resource
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.config import Settings
from app.models.document_chunk import DocumentChunk
from app.services.reranker import RerankerService
from app.services.semantic_search import SemanticSearchResult

REPO_ROOT = Path(__file__).resolve().parents[3]
MODEL_PATH = REPO_ROOT / "storage/models/reranker/model_int8.onnx"
REPORT_PATH = REPO_ROOT / "backend/datasets/evaluation/reports/t260039_multi_worker_report.json"

SAMPLE_PASSAGE = (
    "PostgreSQL hỗ trợ giao dịch ACID đầy đủ, MVCC cho phép đọc ghi đồng thời không khóa, "
    "và mở rộng pgvector giúp lưu trữ và truy vấn vector hiệu năng cao với chỉ mục HNSW."
)


def _get_rss_mb() -> float:
    try:
        with open("/proc/self/status", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024.0, 2)
    except OSError:
        pass
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 2)


def _worker_entrypoint(
    worker_id: int,
    requests_count: int,
    intra_op_threads: int,
    barrier: Any,
    result_queue: Any,
) -> None:
    async def _run() -> dict[str, Any]:
        rss_before_model = _get_rss_mb()
        settings = Settings(
            reranker_enabled=True,
            reranker_model_path=MODEL_PATH,
            reranker_max_concurrency=1,
            reranker_max_queue_size=10,
            reranker_queue_timeout_seconds=10.0,
            reranker_timeout_ms=10000.0,
            reranker_intra_op_threads=intra_op_threads,
            database_url="postgresql+asyncpg://dummy:dummy@localhost/dummy",
            jwt_secret_key="dummy",
        )
        svc = RerankerService(settings=settings)
        ok = svc.initialize_model()
        if not ok:
            raise RuntimeError(f"Worker {worker_id} failed to initialize ONNX model")

        candidates = [
            SemanticSearchResult(
                chunk=DocumentChunk(
                    id=uuid4(),
                    document_id=uuid4(),
                    chunk_index=i,
                    content=f"Đoạn {i}: {SAMPLE_PASSAGE}",
                    char_start=0,
                    char_end=180,
                ),
                similarity=0.8,
            )
            for i in range(10)
        ]
        # Warm-up
        await svc.rerank_candidates(query="PostgreSQL hỗ trợ tính năng gì?", candidates=candidates, limit=5, opt_in=True)
        rss_after_warmup = _get_rss_mb()

        # Synchronize worker start
        barrier.wait(timeout=30.0)

        usage_start = resource.getrusage(resource.RUSAGE_SELF)
        t_wall_start = time.perf_counter()

        latencies: list[float] = []
        fallbacks = 0
        for _ in range(requests_count):
            t0 = time.perf_counter()
            _, is_rr, _ = await svc.rerank_candidates(
                query="PostgreSQL hỗ trợ ACID và pgvector như thế nào?",
                candidates=candidates,
                limit=5,
                opt_in=True,
            )
            latencies.append((time.perf_counter() - t0) * 1000.0)
            if not is_rr:
                fallbacks += 1

        wall_s = time.perf_counter() - t_wall_start
        usage_end = resource.getrusage(resource.RUSAGE_SELF)
        cpu_s = (usage_end.ru_utime - usage_start.ru_utime) + (usage_end.ru_stime - usage_start.ru_stime)
        rss_peak = _get_rss_mb()
        svc.shutdown()

        latencies.sort()
        p50 = latencies[len(latencies) // 2] if latencies else 0.0
        p95 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))] if latencies else 0.0
        return {
            "worker_id": worker_id,
            "requests": requests_count,
            "fallbacks": fallbacks,
            "wall_s": round(wall_s, 3),
            "cpu_s": round(cpu_s, 3),
            "rps": round(requests_count / max(0.001, wall_s), 2),
            "p50_ms": round(p50, 2),
            "p95_ms": round(p95, 2),
            "rss_before_model_mb": rss_before_model,
            "rss_after_warmup_mb": rss_after_warmup,
            "rss_peak_mb": rss_peak,
            "model_memory_delta_mb": round(rss_after_warmup - rss_before_model, 2),
        }

    res = asyncio.run(_run())
    result_queue.put(res)


def run_multi_worker_comparison(requests_per_worker: int = 8, intra_op_threads: int = 4) -> dict[str, Any]:
    if not MODEL_PATH.is_file():
        raise FileNotFoundError(f"ONNX INT8 model missing at {MODEL_PATH}")

    ctx = multiprocessing.get_context("spawn")
    configs = [1, 2]
    summary: dict[str, Any] = {
        "metadata": {
            "task_id": "T260039",
            "logical_cpu_count": os.cpu_count(),
            "intra_op_threads_per_worker": intra_op_threads,
            "requests_per_worker": requests_per_worker,
        },
        "configurations": {},
    }

    for num_workers in configs:
        barrier = ctx.Barrier(num_workers)
        q = ctx.Queue()
        procs = [
            ctx.Process(
                target=_worker_entrypoint,
                args=(wid, requests_per_worker, intra_op_threads, barrier, q),
            )
            for wid in range(num_workers)
        ]
        t0 = time.perf_counter()
        for p in procs:
            p.start()
        worker_results = [q.get(timeout=120.0) for _ in range(num_workers)]
        for p in procs:
            p.join(timeout=30.0)
        total_wall_s = time.perf_counter() - t0

        total_reqs = sum(w["requests"] for w in worker_results)
        agg_rps = round(sum(w["rps"] for w in worker_results), 2)
        total_rss_mb = round(sum(w["rss_peak_mb"] for w in worker_results), 2)
        avg_p50_ms = round(sum(w["p50_ms"] for w in worker_results) / len(worker_results), 2)
        max_p95_ms = round(max(w["p95_ms"] for w in worker_results), 2)

        summary["configurations"][f"{num_workers}_worker"] = {
            "num_workers": num_workers,
            "aggregate_rps": agg_rps,
            "total_requests": total_reqs,
            "total_wall_s": round(total_wall_s, 3),
            "avg_p50_ms": avg_p50_ms,
            "max_p95_ms": max_p95_ms,
            "total_rss_mb": total_rss_mb,
            "workers": worker_results,
        }
        print(
            f"[{num_workers} worker(s) | threads={intra_op_threads}] "
            f"agg_rps={agg_rps} avg_p50={avg_p50_ms}ms max_p95={max_p95_ms}ms total_rss={total_rss_mb}MB"
        )

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="T260039 Multi-Worker Resource Analysis")
    parser.add_argument("--requests", type=int, default=8, help="Requests per worker")
    parser.add_argument("--threads", type=int, default=4, help="Intra-op threads per worker")
    args = parser.parse_args()
    run_multi_worker_comparison(requests_per_worker=args.requests, intra_op_threads=args.threads)


if __name__ == "__main__":
    main()
