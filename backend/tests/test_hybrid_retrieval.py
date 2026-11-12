"""Integration tests for Hybrid Retrieval (T260032).

Verifies:
- Service layer hybrid_search and retrieve_context(mode="hybrid").
- Preservation of dense mode as default.
- Strict workspace isolation across both retrieval branches.
- Handling of single-branch and empty query conditions.
- API endpoint /search/hybrid behavior and response schema.
"""

import os
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.security import create_access_token
from app.db.session import get_session
from app.evaluation.real_fixture_provisioner import verify_database_safety
from app.main import app
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_membership import WorkspaceMembership
from app.services.embedding import get_embedding_service
from app.services.fusion import RetrievalBranch
from app.services.retrieval import (
    RetrievalMode,
    hybrid_search,
    retrieve_context,
)

TEST_DB_URL = os.environ.get(
    "EVAL_TEST_DATABASE_URL",
    (
        "postgresql+asyncpg://ailab:local_only_change_me@/ailab_eval_test?host=/tmp&port=15432"
        if os.path.exists("/tmp/.s.PGSQL.15432")
        else "postgresql+asyncpg://ailab:local_only_change_me@127.0.0.1:15432/ailab_eval_test"
    ),
)


@pytest.fixture(scope="module")
def db_engine():
    verify_database_safety(TEST_DB_URL)
    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    yield engine


@pytest.fixture
async def db_session(db_engine):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest.fixture
async def seeded_hybrid_corpus(db_session: AsyncSession):
    embedding_service = get_embedding_service()

    user = User(
        id=uuid4(),
        email=f"hybrid_test_{uuid4().hex[:8]}@example.com",
        hashed_password="test_hashed_password",
    )
    db_session.add(user)

    ws_a = Workspace(
        id=uuid4(),
        name=f"ws_hybrid_a_{uuid4().hex[:8]}",
        slug=f"ws-hybrid-a-{uuid4().hex[:8]}",
        created_by=user.id,
    )
    ws_b = Workspace(
        id=uuid4(),
        name=f"ws_hybrid_b_{uuid4().hex[:8]}",
        slug=f"ws-hybrid-b-{uuid4().hex[:8]}",
        created_by=user.id,
    )
    db_session.add_all([ws_a, ws_b])
    await db_session.flush()

    membership_a = WorkspaceMembership(
        id=uuid4(),
        workspace_id=ws_a.id,
        user_id=user.id,
        role="owner",
    )
    db_session.add(membership_a)

    doc_a = Document(
        id=uuid4(),
        title="Architecture Doc",
        workspace_id=ws_a.id,
        user_id=user.id,
        source_type="manual",
        status="ready",
    )
    doc_b = Document(
        id=uuid4(),
        title="Isolated Doc",
        workspace_id=ws_b.id,
        user_id=user.id,
        source_type="manual",
        status="ready",
    )
    db_session.add_all([doc_a, doc_b])
    await db_session.flush()

    # Content 1: Semantic match for vector search
    content_dense = "PostgreSQL pgvector extension enables fast similarity search on high-dimensional vectors."
    emb_dense = embedding_service.embed_query(content_dense)
    chunk_dense = DocumentChunk(
        id=uuid4(),
        document_id=doc_a.id,
        chunk_index=0,
        content=content_dense,
        char_start=0,
        char_end=len(content_dense),
        embedding=emb_dense,
    )

    # Content 2: Keyword-specific rare term that vector search might rank low
    content_kw = "System error code ERR_HYBRID_RRF_9981 occurs when buffer allocation fails."
    emb_kw = embedding_service.embed_query(content_kw)
    chunk_kw = DocumentChunk(
        id=uuid4(),
        document_id=doc_a.id,
        chunk_index=1,
        content=content_kw,
        char_start=0,
        char_end=len(content_kw),
        embedding=emb_kw,
    )

    # Content in Workspace B with same keyword
    content_cross = "System error code ERR_HYBRID_RRF_9981 in isolated workspace B."
    emb_cross = embedding_service.embed_query(content_cross)
    chunk_cross = DocumentChunk(
        id=uuid4(),
        document_id=doc_b.id,
        chunk_index=0,
        content=content_cross,
        char_start=0,
        char_end=len(content_cross),
        embedding=emb_cross,
    )

    db_session.add_all([chunk_dense, chunk_kw, chunk_cross])
    await db_session.commit()

    yield {
        "user": user,
        "ws_a": ws_a,
        "ws_b": ws_b,
        "chunk_dense": chunk_dense,
        "chunk_kw": chunk_kw,
        "chunk_cross": chunk_cross,
    }

    # Cleanup
    await db_session.delete(chunk_dense)
    await db_session.delete(chunk_kw)
    await db_session.delete(chunk_cross)
    await db_session.delete(doc_a)
    await db_session.delete(doc_b)
    await db_session.delete(membership_a)
    await db_session.delete(ws_a)
    await db_session.delete(ws_b)
    await db_session.delete(user)
    await db_session.commit()


@pytest.mark.anyio
async def test_hybrid_search_boosts_keyword_matches(db_session: AsyncSession, seeded_hybrid_corpus):
    ws_a_id = seeded_hybrid_corpus["ws_a"].id
    query = "What causes ERR_HYBRID_RRF_9981?"

    fused = await hybrid_search(
        db_session,
        workspace_id=ws_a_id,
        query=query,
        limit=5,
    )

    assert len(fused) >= 1
    # The chunk with exact identifier ERR_HYBRID_RRF_9981 should be at rank 1
    top_result = fused[0]
    assert top_result.chunk.id == seeded_hybrid_corpus["chunk_kw"].id
    assert top_result.provenance in (RetrievalBranch.HYBRID, RetrievalBranch.KEYWORD)
    assert top_result.rrf_score > 0.0


@pytest.mark.anyio
async def test_retrieve_context_modes(db_session: AsyncSession, seeded_hybrid_corpus):
    ws_a_id = seeded_hybrid_corpus["ws_a"].id
    query = "ERR_HYBRID_RRF_9981 buffer allocation"

    # Default mode (Dense)
    ctx_default = await retrieve_context(
        db_session,
        workspace_id=ws_a_id,
        query=query,
        limit=2,
    )
    assert isinstance(ctx_default.sources, list)

    # Explicit Hybrid mode
    ctx_hybrid = await retrieve_context(
        db_session,
        workspace_id=ws_a_id,
        query=query,
        limit=2,
        mode=RetrievalMode.HYBRID,
    )
    assert len(ctx_hybrid.sources) >= 1
    assert ctx_hybrid.sources[0].chunk_id == seeded_hybrid_corpus["chunk_kw"].id
    assert "[Source 1]" in ctx_hybrid.text


@pytest.mark.anyio
async def test_hybrid_search_strict_isolation(db_session: AsyncSession, seeded_hybrid_corpus):
    ws_a_id = seeded_hybrid_corpus["ws_a"].id
    query = "ERR_HYBRID_RRF_9981"

    # Searching in Workspace A must NEVER return Workspace B chunk
    results_a = await hybrid_search(
        db_session,
        workspace_id=ws_a_id,
        query=query,
        limit=10,
    )
    result_chunk_ids = {r.chunk.id for r in results_a}
    assert seeded_hybrid_corpus["chunk_kw"].id in result_chunk_ids
    assert seeded_hybrid_corpus["chunk_cross"].id not in result_chunk_ids


@pytest.mark.anyio
async def test_hybrid_search_api_endpoint(db_session: AsyncSession, seeded_hybrid_corpus):
    user = seeded_hybrid_corpus["user"]
    ws_a = seeded_hybrid_corpus["ws_a"]

    token = create_access_token(subject=str(user.id))

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/v1/search/hybrid",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "query": "ERR_HYBRID_RRF_9981",
                    "workspace_id": str(ws_a.id),
                    "limit": 5,
                    "rrf_k": 60,
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert len(data) >= 1
            top_item = data[0]
            assert top_item["chunk_id"] == str(seeded_hybrid_corpus["chunk_kw"].id)
            assert "rrf_score" in top_item
            assert "provenance" in top_item
            assert top_item["rrf_score"] > 0.0
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.anyio
async def test_search_keyword_chunks_stopword_filtering(
    db_session: AsyncSession, seeded_hybrid_corpus
):
    from app.repositories.document_chunk import search_keyword_chunks

    ws_a_id = seeded_hybrid_corpus["ws_a"].id

    # 1. Query with only stopwords and punctuation should not produce noisy fallback matches
    empty_res = await search_keyword_chunks(
        db_session,
        workspace_id=ws_a_id,
        query="What is the and of in?",
    )
    assert empty_res == []

    # 2. Natural language question with question stopwords + keyword
    kw_res = await search_keyword_chunks(
        db_session,
        workspace_id=ws_a_id,
        query="What is the ERR_HYBRID_RRF_9981 error code?",
    )
    assert len(kw_res) >= 1
    assert kw_res[0][0].id == seeded_hybrid_corpus["chunk_kw"].id

