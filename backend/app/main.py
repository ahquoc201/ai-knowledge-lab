from fastapi import FastAPI

from app.api.v1.auth import router as auth_router
from app.api.v1.documents import router as documents_router
from app.api.v1.health import router as health_router

app = FastAPI(
    title="AI Knowledge Lab",
    description="AI-powered knowledge management platform",
    version="0.1.0",
)

app.include_router(
    health_router,
    prefix="/api/v1",
)

app.include_router(
    auth_router,
    prefix="/api/v1",
)

app.include_router(
    documents_router,
    prefix="/api/v1",
)