import re
import time
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.agent import router as agent_router
from app.api.v1.auth import router as auth_router
from app.api.v1.benchmarks import router as benchmarks_router
from app.api.v1.conversations import router as conversations_router
from app.api.v1.document_chunks import router as document_chunks_router
from app.api.v1.documents import router as documents_router
from app.api.v1.health import router as health_router
from app.api.v1.model_routing import router as model_routing_router
from app.api.v1.models import router as models_router
from app.api.v1.rag import router as rag_router
from app.api.v1.reliability import router as reliability_router
from app.api.v1.search import router as search_router
from app.api.v1.workspaces import router as workspaces_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title="AI Knowledge Lab",
    description="AI-powered knowledge management platform",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


REQUEST_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")


@app.middleware("http")
async def correlation_id_and_observability_middleware(request: Request, call_next):
    raw_request_id = request.headers.get("x-request-id")
    if raw_request_id and REQUEST_ID_REGEX.match(raw_request_id.strip()):
        request_id = raw_request_id.strip()
    else:
        request_id = uuid4().hex

    start_time = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start_time) * 1000
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-Ms"] = f"{duration_ms:.2f}"
    return response

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

app.include_router(
    search_router,
    prefix="/api/v1",
)

app.include_router(
    document_chunks_router,
    prefix="/api/v1",
)

app.include_router(
    conversations_router,
    prefix="/api/v1",
)

app.include_router(
    rag_router,
    prefix="/api/v1",
)

app.include_router(
    workspaces_router,
    prefix="/api/v1",
)

app.include_router(
    agent_router,
    prefix="/api/v1",
)

app.include_router(
    benchmarks_router,
    prefix="/api/v1",
)

app.include_router(
    models_router,
    prefix="/api/v1",
)

app.include_router(
    model_routing_router,
    prefix="/api/v1",
)

app.include_router(
    reliability_router,
    prefix="/api/v1",
)
