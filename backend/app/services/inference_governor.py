"""Inference Concurrency Governor & Admission Control (T260028).

Protects hardware resources (CPU, GPU, VRAM) from Ollama overload by enforcing
strict concurrency budgets, bounded waiting queues, lease expiration, and admission control.
"""

import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import uuid4

from fastapi import HTTPException, status

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class InferenceCapacityExceededError(HTTPException):
    def __init__(self, message: str = "Inference capacity saturated. Queue limit reached.") -> None:
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=message,
            headers={"Retry-After": "5"},
        )


class InferenceQueueTimeoutError(HTTPException):
    def __init__(self, timeout_seconds: float) -> None:
        super().__init__(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Timed out after {timeout_seconds}s waiting for an inference execution slot.",
            headers={"Retry-After": "3"},
        )


@dataclass
class InferenceLease:
    lease_id: str
    caller_info: str
    acquired_at: float
    max_duration_seconds: float

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.acquired_at) > self.max_duration_seconds


@dataclass
class GovernorMetrics:
    active_inferences: int = 0
    queued_requests: int = 0
    total_admitted: int = 0
    total_rejected: int = 0
    total_timeouts: int = 0
    max_concurrency: int = 2
    max_queue_size: int = 10


class InferenceGovernor:
    """Bounded-queue concurrency governor with admission control for Ollama execution."""

    def __init__(
        self,
        max_concurrency: int | None = None,
        max_queue_size: int | None = None,
        queue_timeout_seconds: float | None = None,
    ) -> None:
        settings = get_settings()
        self.max_concurrency = (
            max_concurrency if max_concurrency is not None else settings.ollama_max_concurrency
        )
        self.max_queue_size = (
            max_queue_size if max_queue_size is not None else settings.ollama_max_queue_size
        )
        self.queue_timeout_seconds = (
            queue_timeout_seconds
            if queue_timeout_seconds is not None
            else settings.ollama_queue_timeout_seconds
        )

        self._semaphore = asyncio.Semaphore(self.max_concurrency)
        self._lock = asyncio.Lock()
        self._active_leases: dict[str, InferenceLease] = {}
        self._queued_count = 0
        self._total_admitted = 0
        self._total_rejected = 0
        self._total_timeouts = 0

    @property
    def metrics(self) -> GovernorMetrics:
        return GovernorMetrics(
            active_inferences=len(self._active_leases),
            queued_requests=self._queued_count,
            total_admitted=self._total_admitted,
            total_rejected=self._total_rejected,
            total_timeouts=self._total_timeouts,
            max_concurrency=self.max_concurrency,
            max_queue_size=self.max_queue_size,
        )

    @asynccontextmanager
    async def acquire(
        self,
        caller_info: str = "general_inference",
        timeout: float | None = None,
    ) -> AsyncGenerator[InferenceLease, None]:
        wait_timeout = timeout if timeout is not None else self.queue_timeout_seconds

        # 1. Admission Control check
        async with self._lock:
            if self._queued_count >= self.max_queue_size:
                self._total_rejected += 1
                logger.warning(
                    "Inference admission rejected for '%s': queue full (%d/%d)",
                    caller_info,
                    self._queued_count,
                    self.max_queue_size,
                )
                raise InferenceCapacityExceededError(
                    f"Model inference capacity saturated. Queue limit of {self.max_queue_size} reached."
                )
            self._queued_count += 1

        slot_acquired = False
        start_wait = time.time()
        try:
            # 2. Wait for semaphore slot with bounded timeout
            try:
                await asyncio.wait_for(self._semaphore.acquire(), timeout=wait_timeout)
                slot_acquired = True
                async with self._lock:
                    self._queued_count = max(0, self._queued_count - 1)
            except TimeoutError:
                async with self._lock:
                    self._total_timeouts += 1
                logger.warning(
                    "Inference queue timeout for '%s' after %.2fs",
                    caller_info,
                    time.time() - start_wait,
                )
                raise InferenceQueueTimeoutError(wait_timeout) from None

            # 3. Create Lease
            lease_id = uuid4().hex[:12]
            lease = InferenceLease(
                lease_id=lease_id,
                caller_info=caller_info,
                acquired_at=time.time(),
                max_duration_seconds=120.0,
            )
            async with self._lock:
                self._active_leases[lease_id] = lease
                self._total_admitted += 1

            try:
                yield lease
            finally:
                # 4. Release Lease
                async with self._lock:
                    self._active_leases.pop(lease_id, None)

        finally:
            # 5. Decrement queue count (if failed before slot acquisition) and release semaphore
            if not slot_acquired:
                async with self._lock:
                    self._queued_count = max(0, self._queued_count - 1)
            else:
                self._semaphore.release()


# Global singleton instance
_global_governor: InferenceGovernor | None = None


def get_inference_governor() -> InferenceGovernor:
    global _global_governor
    if _global_governor is None:
        _global_governor = InferenceGovernor()
    return _global_governor
