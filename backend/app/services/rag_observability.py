"""Production RAG Observability & Telemetry (T260039).

Provides:
- Low-overhead, bounded-memory latency tracking (P50, P95, P99, Mean, sample_size).
- Low-cardinality request, failure, cancellation, and reranker degradation counters.
- Sanitized correlation ID helpers and privacy-preserving structured logging
  (never logs raw queries, prompts, document content, embeddings, tokens, or secrets).
"""

import logging
import re
import time
from collections import Counter, deque
from typing import Any
from uuid import uuid4

logger = logging.getLogger("app.rag.observability")

_CORRELATION_RE = re.compile(r"[^a-zA-Z0-9_-]")
_ALLOWED_MODES = frozenset({"dense", "hybrid", "keyword"})


def sanitize_correlation_id(raw_id: str | None) -> str:
    """Return a safe, bounded correlation ID for log tracing."""
    if not raw_id:
        return uuid4().hex[:12]
    cleaned = _CORRELATION_RE.sub("", str(raw_id))[:32]
    return cleaned or uuid4().hex[:12]


def _normalize_mode(mode: str | None) -> str:
    if not mode:
        return "dense"
    norm = str(mode).lower().strip()
    return norm if norm in _ALLOWED_MODES else "other"


def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return round(sorted_vals[0], 3)
    idx = (pct / 100.0) * (len(sorted_vals) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = idx - lo
    val = sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac
    return round(val, 3)


def _summarize_latencies(samples: deque[float]) -> dict[str, Any]:
    n = len(samples)
    if n == 0:
        return {
            "sample_size": 0,
            "mean_ms": 0.0,
            "p50_ms": 0.0,
            "p95_ms": 0.0,
            "p99_ms": 0.0,
        }
    s = sorted(samples)
    return {
        "sample_size": n,
        "mean_ms": round(sum(s) / n, 3),
        "p50_ms": _percentile(s, 50.0),
        "p95_ms": _percentile(s, 95.0),
        "p99_ms": _percentile(s, 99.0),
    }


class RAGObservability:
    """Bounded, low-cardinality operational metrics for the production RAG pipeline."""

    def __init__(self, max_samples: int = 1000) -> None:
        self._max_samples = max_samples
        self.total_requests: int = 0
        self.total_success: int = 0
        self.total_failures: int = 0
        self.total_cancellations: int = 0

        self.streaming_requests: int = 0
        self.non_streaming_requests: int = 0

        self.rerank_opt_in_requests: int = 0
        self.rerank_degraded_requests: int = 0

        self.requests_by_mode: Counter[str] = Counter()
        self.failures_by_stage: Counter[str] = Counter()

        self._retrieval_ms: deque[float] = deque(maxlen=max_samples)
        self._retrieval_by_mode_ms: dict[str, deque[float]] = {
            "dense": deque(maxlen=max_samples),
            "hybrid": deque(maxlen=max_samples),
            "keyword": deque(maxlen=max_samples),
        }
        self._context_assembly_ms: deque[float] = deque(maxlen=max_samples)
        self._llm_generation_ms: deque[float] = deque(maxlen=max_samples)
        self._total_rag_ms: deque[float] = deque(maxlen=max_samples)
        self._streaming_ttft_ms: deque[float] = deque(maxlen=max_samples)

    def record_request(
        self,
        *,
        correlation_id: str,
        mode: str,
        stream: bool,
        rerank_opt_in: bool,
        rerank_used: bool = False,
        rerank_fallback_reason: str | None = None,
        status: str = "success",
        failure_stage: str | None = None,
        retrieval_ms: float | None = None,
        rerank_ms: float | None = None,
        context_assembly_ms: float | None = None,
        llm_generation_ms: float | None = None,
        total_ms: float | None = None,
        ttft_ms: float | None = None,
        source_count: int = 0,
    ) -> None:
        """Record metrics and emit a privacy-preserving structured log line."""
        norm_mode = _normalize_mode(mode)
        self.total_requests += 1
        self.requests_by_mode[norm_mode] += 1

        if stream:
            self.streaming_requests += 1
        else:
            self.non_streaming_requests += 1

        if rerank_opt_in:
            self.rerank_opt_in_requests += 1
            if not rerank_used and status == "success" and rerank_fallback_reason not in (None, "not_requested", "empty_candidates"):
                self.rerank_degraded_requests += 1

        if status == "success":
            self.total_success += 1
        elif status == "cancelled":
            self.total_cancellations += 1
        else:
            self.total_failures += 1
            if failure_stage:
                self.failures_by_stage[failure_stage] += 1

        if retrieval_ms is not None:
            self._retrieval_ms.append(retrieval_ms)
            if norm_mode in self._retrieval_by_mode_ms:
                self._retrieval_by_mode_ms[norm_mode].append(retrieval_ms)
        if context_assembly_ms is not None:
            self._context_assembly_ms.append(context_assembly_ms)
        if llm_generation_ms is not None:
            self._llm_generation_ms.append(llm_generation_ms)
        if total_ms is not None:
            self._total_rag_ms.append(total_ms)
        if ttft_ms is not None:
            self._streaming_ttft_ms.append(ttft_ms)

        # Structured, low-overhead operational log without sensitive user content
        log_fn = logger.info if status == "success" else (logger.warning if status == "cancelled" else logger.error)
        log_fn(
            "[RAG] cid=%s status=%s mode=%s stream=%s rerank_opt_in=%s rerank_used=%s "
            "fallback=%s sources=%d retrieval_ms=%.2f rerank_ms=%.2f context_ms=%.2f "
            "llm_ms=%.2f ttft_ms=%.2f total_ms=%.2f",
            correlation_id,
            status,
            norm_mode,
            stream,
            rerank_opt_in,
            rerank_used,
            rerank_fallback_reason or "none",
            source_count,
            retrieval_ms or 0.0,
            rerank_ms or 0.0,
            context_assembly_ms or 0.0,
            llm_generation_ms or 0.0,
            ttft_ms or 0.0,
            total_ms or 0.0,
        )

    def get_metrics(self) -> dict[str, Any]:
        failure_rate = (self.total_failures / self.total_requests) if self.total_requests > 0 else 0.0
        cancellation_rate = (self.total_cancellations / self.total_requests) if self.total_requests > 0 else 0.0
        rerank_degradation_rate = (
            self.rerank_degraded_requests / self.rerank_opt_in_requests
            if self.rerank_opt_in_requests > 0
            else 0.0
        )

        return {
            "requests": {
                "total": self.total_requests,
                "success": self.total_success,
                "failures": self.total_failures,
                "cancellations": self.total_cancellations,
                "failure_rate": round(failure_rate, 4),
                "cancellation_rate": round(cancellation_rate, 4),
                "streaming": self.streaming_requests,
                "non_streaming": self.non_streaming_requests,
                "by_mode": dict(self.requests_by_mode),
                "failures_by_stage": dict(self.failures_by_stage),
            },
            "reranking_degradation": {
                "opt_in_requests": self.rerank_opt_in_requests,
                "degraded_requests": self.rerank_degraded_requests,
                "degradation_rate": round(rerank_degradation_rate, 4),
            },
            "latency_ms": {
                "retrieval_all": _summarize_latencies(self._retrieval_ms),
                "retrieval_dense": _summarize_latencies(self._retrieval_by_mode_ms["dense"]),
                "retrieval_hybrid": _summarize_latencies(self._retrieval_by_mode_ms["hybrid"]),
                "context_assembly": _summarize_latencies(self._context_assembly_ms),
                "llm_generation": _summarize_latencies(self._llm_generation_ms),
                "total_rag": _summarize_latencies(self._total_rag_ms),
                "streaming_ttft": _summarize_latencies(self._streaming_ttft_ms),
            },
        }

    def reset(self) -> None:
        self.total_requests = 0
        self.total_success = 0
        self.total_failures = 0
        self.total_cancellations = 0
        self.streaming_requests = 0
        self.non_streaming_requests = 0
        self.rerank_opt_in_requests = 0
        self.rerank_degraded_requests = 0
        self.requests_by_mode.clear()
        self.failures_by_stage.clear()
        self._retrieval_ms.clear()
        for q in self._retrieval_by_mode_ms.values():
            q.clear()
        self._context_assembly_ms.clear()
        self._llm_generation_ms.clear()
        self._total_rag_ms.clear()
        self._streaming_ttft_ms.clear()


_global_rag_observability: RAGObservability | None = None


def get_rag_observability() -> RAGObservability:
    """Return process-wide singleton RAGObservability instance."""
    global _global_rag_observability
    if _global_rag_observability is None:
        _global_rag_observability = RAGObservability()
    return _global_rag_observability


def elapsed_ms(t_start: float) -> float:
    """Return elapsed milliseconds from a perf_counter timestamp."""
    return (time.perf_counter() - t_start) * 1000.0
