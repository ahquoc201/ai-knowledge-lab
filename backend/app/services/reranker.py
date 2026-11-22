"""Production ONNX INT8 Cross-Encoder Reranker Service (T260038).

Provides:
- Non-blocking CPU inference adapter for multilingual Cross-Encoder reranking.
- Strictly bounded concurrency with admission control and queue-wait limits.
- Concurrency permit release tied to worker completion (prevents CPU thread accumulation on timeout).
- Fail-safe fallback to authorized first-stage retrieval on any failure.
- Preserved cosine similarity, tenant isolation, and deterministic tie-breaking.
- Minimal production observability and telemetry (no raw queries or text in logs).
"""

import asyncio
import hashlib
import logging
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

MAX_SEQ_LENGTH = 512


def compute_file_sha256(file_path: Path) -> str:
    """Calculate SHA256 digest of a local file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            sha256.update(chunk)
    return sha256.hexdigest()


class RerankerError(Exception):
    """Base exception for reranker service."""


class RerankerNotReadyError(RerankerError):
    """Raised when the reranker model is not loaded or unavailable."""


class RerankerCapacityError(RerankerError):
    """Raised when concurrency or waiting queue capacity is saturated."""


class RerankerTimeoutError(RerankerError):
    """Raised when waiting in queue or model inference exceeds timeout."""


class RerankerInferenceError(RerankerError):
    """Raised when ONNX inference fails unexpectedly."""


@dataclass(frozen=True, slots=True)
class RerankedSearchResult:
    """Wraps retrieval candidate with dedicated Cross-Encoder rerank score.

    Preserves true cosine similarity or RRF score, never conflating rerank score with similarity.
    """

    chunk: Any
    similarity: float
    document_title: str | None = None
    rerank_score: float | None = None
    rrf_score: float | None = None


class RerankerTelemetry:
    """Tracks thread-safe telemetry and latency distributions for the reranker service."""

    def __init__(self, history_maxlen: int = 1000) -> None:
        self.total_requests: int = 0
        self.total_opt_in: int = 0
        self.total_success: int = 0
        self.total_fallback: int = 0
        self.fallback_reasons: dict[str, int] = {}
        self.queue_timeouts: int = 0
        self.inference_timeouts: int = 0
        self.capacity_rejections: int = 0
        self.init_success_count: int = 0
        self.init_failure_count: int = 0
        self._tokenization_latencies: deque[float] = deque(maxlen=history_maxlen)
        self._inference_latencies: deque[float] = deque(maxlen=history_maxlen)
        self._total_latencies: deque[float] = deque(maxlen=history_maxlen)
        self._queue_wait_latencies: deque[float] = deque(maxlen=history_maxlen)

    def record_init(self, success: bool) -> None:
        if success:
            self.init_success_count += 1
        else:
            self.init_failure_count += 1

    def record_request(self, opt_in: bool) -> None:
        self.total_requests += 1
        if opt_in:
            self.total_opt_in += 1

    def record_success(
        self,
        *,
        queue_wait_ms: float,
        tokenize_ms: float,
        inference_ms: float,
        total_ms: float,
    ) -> None:
        self.total_success += 1
        self._queue_wait_latencies.append(queue_wait_ms)
        self._tokenization_latencies.append(tokenize_ms)
        self._inference_latencies.append(inference_ms)
        self._total_latencies.append(total_ms)

    def record_fallback(self, reason: str) -> None:
        self.total_fallback += 1
        self.fallback_reasons[reason] = self.fallback_reasons.get(reason, 0) + 1
        if "queue_timeout" in reason:
            self.queue_timeouts += 1
        elif "inference_timeout" in reason or "timeout" in reason:
            self.inference_timeouts += 1
        elif "capacity" in reason:
            self.capacity_rejections += 1

    def get_metrics(
        self,
        *,
        enabled: bool,
        is_ready: bool,
        active_inferences: int,
        queued_requests: int,
    ) -> dict[str, Any]:
        """Return snapshot of reranker operational metrics."""

        def _p50(data: deque[float]) -> float:
            return round(float(np.percentile(list(data), 50)), 2) if data else 0.0

        def _p95(data: deque[float]) -> float:
            return round(float(np.percentile(list(data), 95)), 2) if data else 0.0

        opt_in_denom = self.total_opt_in if self.total_opt_in > 0 else 1

        return {
            "enabled": enabled,
            "is_ready": is_ready,
            "active_inferences": active_inferences,
            "queued_requests": queued_requests,
            "total_requests": self.total_requests,
            "total_opt_in": self.total_opt_in,
            "total_success": self.total_success,
            "total_fallback": self.total_fallback,
            "fallback_rate": round(self.total_fallback / opt_in_denom, 4) if self.total_opt_in > 0 else 0.0,
            "fallback_reasons": dict(self.fallback_reasons),
            "queue_timeouts": self.queue_timeouts,
            "queue_timeout_rate": round(self.queue_timeouts / opt_in_denom, 4) if self.total_opt_in > 0 else 0.0,
            "inference_timeouts": self.inference_timeouts,
            "inference_timeout_rate": round(self.inference_timeouts / opt_in_denom, 4) if self.total_opt_in > 0 else 0.0,
            "capacity_rejections": self.capacity_rejections,
            "init_success_count": self.init_success_count,
            "init_failure_count": self.init_failure_count,
            "p50_queue_wait_ms": _p50(self._queue_wait_latencies),
            "p95_queue_wait_ms": _p95(self._queue_wait_latencies),
            "p50_tokenization_ms": _p50(self._tokenization_latencies),
            "p50_inference_ms": _p50(self._inference_latencies),
            "p95_inference_ms": _p95(self._inference_latencies),
            "p50_total_rerank_ms": _p50(self._total_latencies),
            "p95_total_rerank_ms": _p95(self._total_latencies),
        }

    def reset(self) -> None:
        self.total_requests = 0
        self.total_opt_in = 0
        self.total_success = 0
        self.total_fallback = 0
        self.fallback_reasons.clear()
        self.queue_timeouts = 0
        self.inference_timeouts = 0
        self.capacity_rejections = 0
        self.init_success_count = 0
        self.init_failure_count = 0
        self._tokenization_latencies.clear()
        self._inference_latencies.clear()
        self._total_latencies.clear()
        self._queue_wait_latencies.clear()


class RerankerService:
    """Production ONNX Runtime Cross-Encoder Reranker service with bounded CPU concurrency."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.model_path = Path(self.settings.reranker_model_path)
        self.max_concurrency = max(1, self.settings.reranker_max_concurrency)
        self.max_queue_size = max(1, self.settings.reranker_max_queue_size)
        self.queue_timeout_seconds = self.settings.reranker_queue_timeout_seconds
        self.timeout_seconds = self.settings.reranker_timeout_ms / 1000.0
        self.intra_op_threads = self.settings.reranker_intra_op_threads

        self.telemetry = RerankerTelemetry()

        self._session: Any | None = None
        self._tokenizer: Any | None = None
        self._is_ready: bool = False
        self._init_error: str | None = None

        self._semaphore: asyncio.Semaphore | None = None
        self._active_inferences: int = 0
        self._queued_requests: int = 0

        self._executor = ThreadPoolExecutor(
            max_workers=self.max_concurrency,
            thread_name_prefix="onnx_reranker",
        )

    @property
    def is_ready(self) -> bool:
        return self._is_ready

    @property
    def is_enabled(self) -> bool:
        return bool(self.settings.reranker_enabled)

    def initialize_model(self) -> bool:
        """Load tokenizer and ONNX Runtime session if not already initialized.

        Gracefully sets is_ready=False without throwing if artifacts are missing or invalid.
        """
        if self._is_ready and self._session is not None and self._tokenizer is not None:
            return True

        if not self.model_path.is_file():
            self._is_ready = False
            self._init_error = f"Model artifact missing at {self.model_path}"
            self.telemetry.record_init(False)
            logger.warning("[Reranker] Model file not found at %s. Reranker disabled.", self.model_path)
            return False

        if self.settings.reranker_expected_sha256:
            try:
                actual_sha = compute_file_sha256(self.model_path)
                if actual_sha.lower() != self.settings.reranker_expected_sha256.lower():
                    self._is_ready = False
                    self._init_error = f"SHA256 mismatch: expected {self.settings.reranker_expected_sha256}, got {actual_sha}"
                    self.telemetry.record_init(False)
                    logger.error("[Reranker] Model integrity failure: %s", self._init_error)
                    return False
            except OSError as exc:
                self._is_ready = False
                self._init_error = f"Error reading model for checksum: {exc}"
                self.telemetry.record_init(False)
                return False

        try:
            from transformers import AutoTokenizer

            # Load tokenizer strictly offline without automated network downloads
            self._tokenizer = AutoTokenizer.from_pretrained(
                self.settings.reranker_model_name,
                local_files_only=True,
            )

            import onnxruntime as ort

            opts = ort.SessionOptions()
            opts.intra_op_num_threads = self.intra_op_threads
            opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

            self._session = ort.InferenceSession(
                str(self.model_path),
                sess_options=opts,
                providers=["CPUExecutionProvider"],
            )

            self._is_ready = True
            self._init_error = None
            self.telemetry.record_init(True)
            logger.info(
                "[Reranker] Initialized ONNX INT8 session successfully (threads=%d, path=%s)",
                self.intra_op_threads,
                self.model_path,
            )
            return True
        except (OSError, RuntimeError, ValueError) as exc:
            self._is_ready = False
            self._init_error = str(exc)
            self.telemetry.record_init(False)
            logger.exception("[Reranker] Failed to initialize model session")
            return False

    def _sync_predict(
        self,
        pairs: list[tuple[str, str]],
    ) -> tuple[list[float], dict[str, float]]:
        """Worker thread inference execution: tokenization + ONNX forward pass."""
        if not pairs:
            return [], {"tokenize_ms": 0.0, "inference_ms": 0.0, "total_ms": 0.0}

        t_start = time.perf_counter()

        # 1. Tokenize
        t_tok_start = time.perf_counter()
        queries = [p[0] for p in pairs]
        passages = [p[1] for p in pairs]

        inputs = self._tokenizer(
            queries,
            passages,
            return_tensors="np",
            padding=True,
            truncation=True,
            max_length=MAX_SEQ_LENGTH,
        )
        tokenize_ms = (time.perf_counter() - t_tok_start) * 1000.0

        # 2. ONNX Forward Pass
        t_inf_start = time.perf_counter()
        ort_inputs = {
            "input_ids": inputs["input_ids"],
            "attention_mask": inputs["attention_mask"],
        }
        outputs = self._session.run(["logits"], ort_inputs)
        logits = outputs[0].squeeze(-1)
        if logits.ndim == 0:
            logits = np.expand_dims(logits, axis=0)

        inference_ms = (time.perf_counter() - t_inf_start) * 1000.0
        total_ms = (time.perf_counter() - t_start) * 1000.0

        timing = {
            "tokenize_ms": round(tokenize_ms, 3),
            "inference_ms": round(inference_ms, 3),
            "total_ms": round(total_ms, 3),
        }
        return [float(s) for s in logits], timing

    async def rerank_candidates(
        self,
        *,
        query: str,
        candidates: list[Any],
        limit: int = 5,
        opt_in: bool = False,
    ) -> tuple[list[Any], bool, str | None]:
        """Rerank candidates using ONNX INT8 Cross-Encoder with fail-safe fallback.

        Returns:
            tuple of (final_candidates, is_reranked, fallback_reason)
        """
        self.telemetry.record_request(opt_in)

        # 1. Check opt-in & server enablement
        if not opt_in:
            return candidates[:limit], False, "not_requested"

        if not self.is_enabled:
            self.telemetry.record_fallback("disabled_by_server")
            return candidates[:limit], False, "disabled_by_server"

        if not candidates:
            return [], False, "empty_candidates"

        # 2. Check model readiness
        if not self._is_ready and not self.initialize_model():
            self.telemetry.record_fallback("model_not_ready")
            return candidates[:limit], False, "model_not_ready"

        # 3. Admission Control: Check waiting queue saturation
        if self._queued_requests >= self.max_queue_size:
            logger.warning("[Reranker] Admission rejected: queue saturated (%d/%d)", self._queued_requests, self.max_queue_size)
            self.telemetry.record_fallback("capacity_saturated")
            return candidates[:limit], False, "capacity_saturated"

        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.max_concurrency)

        # 4. Acquire Concurrency Slot with Queue Timeout
        self._queued_requests += 1
        t_queue_start = time.perf_counter()
        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout=self.queue_timeout_seconds)
        except TimeoutError:
            logger.warning(
                "[Reranker] Queue wait timed out after %.2fs (%d waiting)",
                self.queue_timeout_seconds,
                self._queued_requests,
            )
            self.telemetry.record_fallback("queue_timeout")
            return candidates[:limit], False, "queue_timeout"
        finally:
            self._queued_requests -= 1

        queue_wait_ms = (time.perf_counter() - t_queue_start) * 1000.0

        # 5. Dispatch inference to worker thread pool
        # Bounded concurrency rule: Hold permit until underlying OS thread worker completes!
        permit_released = False
        loop = asyncio.get_running_loop()

        def _release_permit() -> None:
            nonlocal permit_released
            if not permit_released:
                permit_released = True
                self._active_inferences = max(0, self._active_inferences - 1)
                if self._semaphore is not None:
                    self._semaphore.release()

        def _on_thread_worker_done(_fut: Any) -> None:
            # Invoked on OS worker thread upon completion; release permit thread-safely on event loop
            if loop.is_running() and not loop.is_closed():
                loop.call_soon_threadsafe(_release_permit)

        self._active_inferences += 1
        pairs = [(query, c.chunk.content) for c in candidates]

        try:
            # Submit directly to ThreadPoolExecutor to track true OS worker completion
            thread_future = self._executor.submit(self._sync_predict, pairs)
            thread_future.add_done_callback(_on_thread_worker_done)
            asyncio_future = asyncio.wrap_future(thread_future, loop=loop)

            scores, timing = await asyncio.wait_for(
                asyncio_future,
                timeout=self.timeout_seconds,
            )
        except TimeoutError:
            logger.warning("[Reranker] Inference timed out after %.2fs. Falling back.", self.timeout_seconds)
            self.telemetry.record_fallback("inference_timeout")
            return candidates[:limit], False, "inference_timeout"
        except asyncio.CancelledError:
            logger.info("[Reranker] Inference request cancelled by client.")
            self.telemetry.record_fallback("cancelled")
            raise
        except (RuntimeError, ValueError, OSError):
            logger.exception("[Reranker] Inference error. Falling back.")
            _release_permit()
            self.telemetry.record_fallback("inference_error")
            return candidates[:limit], False, "inference_error"

        # 6. Rank candidates deterministically by (rerank_score desc, chunk_id asc)
        if len(scores) != len(candidates):
            logger.error("[Reranker] Output size mismatch (%d != %d). Falling back.", len(scores), len(candidates))
            self.telemetry.record_fallback("output_mismatch")
            return candidates[:limit], False, "output_mismatch"

        scored_candidates = []
        for candidate, score in zip(candidates, scores):
            reranked_item = RerankedSearchResult(
                chunk=candidate.chunk,
                similarity=candidate.similarity,
                document_title=candidate.document_title,
                rerank_score=score,
                rrf_score=getattr(candidate, "rrf_score", None),
            )
            scored_candidates.append(reranked_item)

        # Deterministic tie-breaking: score desc, then chunk UUID asc
        scored_candidates.sort(key=lambda x: (-x.rerank_score, str(x.chunk.id)))

        self.telemetry.record_success(
            queue_wait_ms=queue_wait_ms,
            tokenize_ms=timing["tokenize_ms"],
            inference_ms=timing["inference_ms"],
            total_ms=timing["total_ms"],
        )

        return scored_candidates[:limit], True, None

    def get_metrics(self) -> dict[str, Any]:
        return self.telemetry.get_metrics(
            enabled=self.is_enabled,
            is_ready=self.is_ready,
            active_inferences=self._active_inferences,
            queued_requests=self._queued_requests,
        )

    def shutdown(self) -> None:
        """Non-blocking release of runtime resources upon application shutdown.

        Cancels any unstarted queued tasks and closes inference sessions without
        blocking the event loop. Already-executing worker threads finish their active pass.
        """
        self._is_ready = False
        self._session = None
        self._tokenizer = None
        self._executor.shutdown(wait=False, cancel_futures=True)


_global_reranker: RerankerService | None = None


def get_reranker_service() -> RerankerService:
    """Retrieve process-wide singleton RerankerService."""
    global _global_reranker
    if _global_reranker is None:
        _global_reranker = RerankerService()
    return _global_reranker


def set_reranker_service(instance: RerankerService | None) -> None:
    """Override singleton instance (used in automated tests)."""
    global _global_reranker
    if _global_reranker is not None and instance is not _global_reranker:
        try:
            _global_reranker.shutdown()
        except (OSError, RuntimeError) as exc:
            logger.debug("[Reranker] Cleanup notice on shutdown: %s", exc)
    _global_reranker = instance
