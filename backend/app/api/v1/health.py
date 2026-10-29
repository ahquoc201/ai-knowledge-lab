import logging
from datetime import UTC, datetime
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_session
from app.services.rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/health",
    tags=["Health"],
)


@router.get("")
async def health_check():
    """Liveness probe: verifies basic backend process responsiveness."""
    return {
        "status": "ok",
        "service": "AI Knowledge Lab Backend",
    }


@router.get("/database")
async def database_health_check(
    session: Annotated[AsyncSession, Depends(get_session)],
):
    await session.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "database": "connected",
    }


@router.get("/ready")
async def readiness_check(
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Readiness probe: distinguishes healthy, degraded, and unavailable states."""
    settings = get_settings()
    now_str = datetime.now(UTC).isoformat()
    components: dict[str, dict] = {}

    # 1. PostgreSQL check (Critical - core data and auth dependency)
    try:
        await session.execute(text("SELECT 1"))
        components["postgres"] = {"status": "up"}
    except Exception as exc:
        logger.error("Health check failed on PostgreSQL: %s", exc)
        components["postgres"] = {"status": "down", "error": str(exc)}
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "unhealthy",
                "timestamp": now_str,
                "components": components,
                "reason": "Core database is unavailable",
            },
        ) from exc

    # 2. Redis Rate Limiter check (Non-critical - automatically falls back to in-memory)
    limiter = get_rate_limiter()
    redis_active = limiter.is_redis_active()
    components["redis"] = {
        "status": "up" if redis_active else "offline",
        "mode": "distributed_redis" if redis_active else "local_in_memory_fallback",
    }

    # 3. Ollama Inference check (Degraded if unreachable, but auth/docs remain fully functional)
    ollama_ok = False
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            ollama_ok = resp.status_code == 200
    except (httpx.HTTPError, OSError):
        ollama_ok = False

    components["ollama"] = {
        "status": "up" if ollama_ok else "unreachable",
        "model": settings.ollama_model,
        "base_url": settings.ollama_base_url,
    }

    if not redis_active or not ollama_ok:
        overall_status = "degraded"
        degraded_reasons = []
        if not redis_active:
            degraded_reasons.append("Distributed rate limiter offline (using in-memory fallback)")
        if not ollama_ok:
            degraded_reasons.append("AI model service unreachable")
        status_message = "; ".join(degraded_reasons)
    else:
        overall_status = "healthy"
        status_message = "All systems operational"

    return {
        "status": overall_status,
        "timestamp": now_str,
        "components": components,
        "message": status_message,
    }
