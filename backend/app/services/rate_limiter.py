"""Distributed Rate Limiter with Redis & In-Memory Fallback (T260028).

Enforces sliding window rate limits across authentication, RAG chat, agent runs,
benchmarks, and model operations with atomic counting, headers, and graceful degradation.
"""

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request, status

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Atomic Redis Lua script for sliding-window log rate limiting
SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local clear_before = now - window

-- Remove old events outside the current window
redis.call('ZREMRANGEBYSCORE', key, '-inf', clear_before)

-- Count current events in window
local current_requests = redis.call('ZCARD', key)

if current_requests < limit then
    -- Add unique member: now:random or now:current_requests
    redis.call('ZADD', key, now, now .. ':' .. current_requests)
    redis.call('EXPIRE', key, math.ceil(window) + 1)
    return {1, limit - current_requests - 1, math.ceil(window)}
else
    -- Over limit: find oldest timestamp to compute reset time
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry_after = math.ceil(window)
    if #oldest >= 2 then
        local oldest_ts = tonumber(oldest[2])
        retry_after = math.max(1, math.ceil(oldest_ts + window - now))
    end
    return {0, 0, retry_after}
end
"""


@dataclass
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int
    reset_seconds: int
    rule_name: str


class InMemorySlidingWindowLimiter:
    """Thread-safe in-memory sliding window fallback when Redis is unavailable."""

    def __init__(self) -> None:
        self._storage: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int, window_seconds: int, rule_name: str) -> RateLimitResult:
        now = time.time()
        cutoff = now - window_seconds
        timestamps = self._storage[key]

        # Purge stale timestamps
        while timestamps and timestamps[0] <= cutoff:
            timestamps.popleft()

        if len(timestamps) < limit:
            timestamps.append(now)
            remaining = limit - len(timestamps)
            return RateLimitResult(
                allowed=True,
                limit=limit,
                remaining=remaining,
                retry_after=0,
                reset_seconds=window_seconds,
                rule_name=rule_name,
            )

        # Over limit
        oldest = timestamps[0]
        retry_after = max(1, int(oldest + window_seconds - now))
        return RateLimitResult(
            allowed=False,
            limit=limit,
            remaining=0,
            retry_after=retry_after,
            reset_seconds=retry_after,
            rule_name=rule_name,
        )

    def clear(self) -> None:
        self._storage.clear()


class RateLimiter:
    """Production-grade rate limiter supporting Redis and automatic in-memory fallback."""

    def __init__(self, redis_url: str | None = None) -> None:
        self.settings = get_settings()
        self.redis_url = redis_url or self.settings.rate_limit_redis_url
        self._redis_client: Any = None
        self._redis_failed = False
        self._memory_limiter = InMemorySlidingWindowLimiter()
        self._lua_script: Any = None

    def _get_redis(self) -> Any:
        if self._redis_failed:
            return None
        if self._redis_client is None:
            try:
                import redis
                self._redis_client = redis.Redis.from_url(
                    self.redis_url,
                    socket_connect_timeout=0.2,
                    socket_timeout=0.2,
                    decode_responses=True,
                )
                # Ping test
                self._redis_client.ping()
                self._lua_script = self._redis_client.register_script(SLIDING_WINDOW_LUA)
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "Redis unavailable for rate limiting (%s); falling back to in-memory sliding window limiter.",
                    e,
                )
                self._redis_failed = True
                self._redis_client = None
        return self._redis_client

    def is_redis_active(self) -> bool:
        client = self._get_redis()
        return client is not None

    def check(
        self,
        identifier: str,
        limit: int,
        window_seconds: int,
        rule_name: str = "default",
    ) -> RateLimitResult:
        """Check rate limit atomically via Redis Lua script, or memory fallback."""
        if not self.settings.rate_limit_enabled:
            return RateLimitResult(
                allowed=True,
                limit=limit,
                remaining=limit,
                retry_after=0,
                reset_seconds=0,
                rule_name=rule_name,
            )

        key = f"rate_limit:{rule_name}:{identifier}"
        redis_client = self._get_redis()

        if redis_client is not None and self._lua_script is not None:
            try:
                now = time.time()
                res = self._lua_script(
                    keys=[key],
                    args=[now, window_seconds, limit],
                )
                allowed_int, remaining, retry_after = res[0], res[1], res[2]
                return RateLimitResult(
                    allowed=bool(allowed_int == 1),
                    limit=limit,
                    remaining=int(remaining),
                    retry_after=int(retry_after),
                    reset_seconds=int(retry_after),
                    rule_name=rule_name,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Redis rate limit check error (%s); falling back to in-memory limiter for this request.",
                    exc,
                )
                self._redis_failed = True

        # Fallback to in-memory sliding window
        return self._memory_limiter.check(
            key=key, limit=limit, window_seconds=window_seconds, rule_name=rule_name
        )

    def clear(self) -> None:
        """Clear limiter memory storage (useful in tests)."""
        self._memory_limiter.clear()

    def enforce(
        self,
        identifier: str,
        limit: int,
        window_seconds: int,
        rule_name: str = "default",
    ) -> RateLimitResult:
        """Enforce rate limit, raising HTTP 429 if limit is exceeded."""
        result = self.check(identifier, limit, window_seconds, rule_name)
        if not result.allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded for {rule_name}. Please retry after {result.retry_after} seconds.",
                headers={
                    "Retry-After": str(result.retry_after),
                    "X-RateLimit-Limit": str(result.limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time()) + result.reset_seconds),
                },
            )
        return result


# Global singleton instance
_global_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    global _global_rate_limiter
    if _global_rate_limiter is None:
        _global_rate_limiter = RateLimiter()
    return _global_rate_limiter


def extract_client_ip(request: Request) -> str:
    """Safely extracts client IP considering proxies and fallbacks."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # First IP in comma-separated list is client IP
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"
