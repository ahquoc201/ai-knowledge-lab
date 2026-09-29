from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session

router = APIRouter(
    prefix="/health",
    tags=["Health"],
)


@router.get("")
async def health_check():
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