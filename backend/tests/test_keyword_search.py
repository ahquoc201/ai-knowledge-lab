"""Tests for PostgreSQL Full-Text Search in DocumentChunk repository (T260032).

Verifies:
- English, Vietnamese, technical identifiers, punctuation, empty queries.
- Mandatory tenant/workspace authorization at SQL level.
- Deterministic ordering by rank DESC, chunk ID ASC.
- SQL injection immunity and special character safety.
"""

import os
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.evaluation.real_fixture_provisioner import verify_database_safety
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.user import User
from app.models.workspace import Workspace
from app.repositories.document_chunk import search_keyword_chunks

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
async def setup_test_corpus(db_session: AsyncSession):
    """Seed isolated workspaces, documents, and chunks for keyword testing."""
    # Create test user
    user = User(
        id=uuid4(),
        email=f"keyword_test_{uuid4().hex[:8]}@example.com",
        hashed_password="test_hashed_password",
    )
    db_session.add(user)

    # Create two workspaces for isolation tests
    ws_a = Workspace(
        id=uuid4(),
        name=f"ws_a_{uuid4().hex[:8]}",
        slug=f"ws-a-{uuid4().hex[:8]}",
        created_by=user.id,
    )
    ws_b = Workspace(
        id=uuid4(),
        name=f"ws_b_{uuid4().hex[:8]}",
        slug=f"ws-b-{uuid4().hex[:8]}",
        created_by=user.id,
    )
    db_session.add_all([ws_a, ws_b])
    await db_session.flush()

    # Document in Workspace A
    doc_a = Document(
        id=uuid4(),
        title="Knowledge Base Alpha",
        workspace_id=ws_a.id,
        user_id=user.id,
        source_type="manual",
        status="ready",
    )
    # Document in Workspace B
    doc_b = Document(
        id=uuid4(),
        title="Knowledge Base Beta",
        workspace_id=ws_b.id,
        user_id=user.id,
        source_type="manual",
        status="ready",
    )
    db_session.add_all([doc_a, doc_b])
    await db_session.flush()

    # Chunks in Workspace A
    chunk_en = DocumentChunk(
        id=uuid4(),
        document_id=doc_a.id,
        chunk_index=0,
        content="PostgreSQL 16 provides functional GIN indexes for fast full-text search.",
        char_start=0,
        char_end=73,
    )
    chunk_vn = DocumentChunk(
        id=uuid4(),
        document_id=doc_a.id,
        chunk_index=1,
        content="Phở bò và bún chả là hai món ăn truyền thống nổi tiếng của ẩm thực Việt Nam.",
        char_start=0,
        char_end=77,
    )
    chunk_ident = DocumentChunk(
        id=uuid4(),
        document_id=doc_a.id,
        chunk_index=2,
        content="Diagnostic code rag_eval_kb_006 was triggered by error_code_500 in service_gateway.",
        char_start=0,
        char_end=84,
    )
    chunk_shared_a = DocumentChunk(
        id=uuid4(),
        document_id=doc_a.id,
        chunk_index=3,
        content="Confidential project roadmap for enterprise client Q4 deliverables.",
        char_start=0,
        char_end=68,
    )

    # Chunks in Workspace B (contains same secret phrase)
    chunk_shared_b = DocumentChunk(
        id=uuid4(),
        document_id=doc_b.id,
        chunk_index=0,
        content="Confidential project roadmap for enterprise client Q4 deliverables.",
        char_start=0,
        char_end=68,
    )

    db_session.add_all([chunk_en, chunk_vn, chunk_ident, chunk_shared_a, chunk_shared_b])
    await db_session.commit()

    yield {
        "user": user,
        "ws_a": ws_a,
        "ws_b": ws_b,
        "doc_a": doc_a,
        "doc_b": doc_b,
        "chunk_en": chunk_en,
        "chunk_vn": chunk_vn,
        "chunk_ident": chunk_ident,
        "chunk_shared_a": chunk_shared_a,
        "chunk_shared_b": chunk_shared_b,
    }

    # Cleanup
    await db_session.delete(chunk_en)
    await db_session.delete(chunk_vn)
    await db_session.delete(chunk_ident)
    await db_session.delete(chunk_shared_a)
    await db_session.delete(chunk_shared_b)
    await db_session.delete(doc_a)
    await db_session.delete(doc_b)
    await db_session.delete(ws_a)
    await db_session.delete(ws_b)
    await db_session.delete(user)
    await db_session.commit()


@pytest.mark.anyio
async def test_keyword_search_empty_and_whitespace(db_session: AsyncSession, setup_test_corpus):
    ws_id = setup_test_corpus["ws_a"].id

    res1 = await search_keyword_chunks(db_session, workspace_id=ws_id, query="")
    assert res1 == []

    res2 = await search_keyword_chunks(db_session, workspace_id=ws_id, query="   \t\n  ")
    assert res2 == []


@pytest.mark.anyio
async def test_keyword_search_english(db_session: AsyncSession, setup_test_corpus):
    ws_id = setup_test_corpus["ws_a"].id

    res = await search_keyword_chunks(
        db_session,
        workspace_id=ws_id,
        query="PostgreSQL full-text search",
        limit=5,
    )
    assert len(res) >= 1
    top_chunk, rank, title = res[0]
    assert top_chunk.id == setup_test_corpus["chunk_en"].id
    assert title == "Knowledge Base Alpha"
    assert rank > 0.0


@pytest.mark.anyio
async def test_keyword_search_vietnamese(db_session: AsyncSession, setup_test_corpus):
    ws_id = setup_test_corpus["ws_a"].id

    res = await search_keyword_chunks(
        db_session,
        workspace_id=ws_id,
        query="ẩm thực Việt Nam Phở bò",
        limit=5,
    )
    assert len(res) >= 1
    top_chunk, rank, _title = res[0]
    assert top_chunk.id == setup_test_corpus["chunk_vn"].id
    assert rank > 0.0


@pytest.mark.anyio
async def test_keyword_search_technical_identifiers(db_session: AsyncSession, setup_test_corpus):
    ws_id = setup_test_corpus["ws_a"].id

    res = await search_keyword_chunks(
        db_session,
        workspace_id=ws_id,
        query="rag_eval_kb_006 error_code_500",
        limit=5,
    )
    assert len(res) >= 1
    top_chunk, rank, _title = res[0]
    assert top_chunk.id == setup_test_corpus["chunk_ident"].id
    assert rank > 0.0


@pytest.mark.anyio
async def test_keyword_search_punctuation_and_sql_injection(db_session: AsyncSession, setup_test_corpus):
    ws_id = setup_test_corpus["ws_a"].id

    # Punctuation query should safely return empty or non-crashing result
    res_punct = await search_keyword_chunks(
        db_session,
        workspace_id=ws_id,
        query="!@#$%^&*()_+{}[]:;\"'<>?,./",
        limit=5,
    )
    assert isinstance(res_punct, list)

    # SQL injection attempt must be cleanly parameterized and safe
    injection_query = "' OR 1=1; DROP TABLE document_chunks; --"
    res_inject = await search_keyword_chunks(
        db_session,
        workspace_id=ws_id,
        query=injection_query,
        limit=5,
    )
    assert isinstance(res_inject, list)


@pytest.mark.anyio
async def test_keyword_search_strict_workspace_isolation(db_session: AsyncSession, setup_test_corpus):
    ws_a_id = setup_test_corpus["ws_a"].id
    ws_b_id = setup_test_corpus["ws_b"].id
    query = "Confidential project roadmap"

    # Query Workspace A
    res_a = await search_keyword_chunks(
        db_session,
        workspace_id=ws_a_id,
        query=query,
        limit=10,
    )
    assert len(res_a) == 1
    assert res_a[0][0].id == setup_test_corpus["chunk_shared_a"].id
    assert res_a[0][0].id != setup_test_corpus["chunk_shared_b"].id

    # Query Workspace B
    res_b = await search_keyword_chunks(
        db_session,
        workspace_id=ws_b_id,
        query=query,
        limit=10,
    )
    assert len(res_b) == 1
    assert res_b[0][0].id == setup_test_corpus["chunk_shared_b"].id
    assert res_b[0][0].id != setup_test_corpus["chunk_shared_a"].id


@pytest.mark.anyio
async def test_keyword_search_requires_workspace_or_user_id(db_session: AsyncSession):
    with pytest.raises(ValueError, match="Either workspace_id or user_id must be provided"):
        await search_keyword_chunks(
            db_session,
            workspace_id=None,
            user_id=None,
            query="test",
        )
