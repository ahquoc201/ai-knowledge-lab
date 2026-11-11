"""Provision and clean up isolated synthetic RAG fixtures for real-stack evaluation (T260031).

Ensures 100% data safety:
- Prohibits provisioning into historical production 'ailab' database.
- Provisions deterministic synthetic workspaces and documents with real pgvector embeddings.
- Maps fixture keys to runtime database UUIDs.
- Automatically cleans up evaluation artifacts upon exit.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from secrets import token_urlsafe
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.document_status import DocumentStatus
from app.core.security import hash_password
from app.core.workspace_role import WorkspaceRole, WorkspaceStatus
from app.evaluation.rag_dataset import RAGDatasetManifest
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_membership import WorkspaceMembership
from app.services.chunking import chunk_text
from app.services.embedding import get_embedding_service


def verify_database_safety(url_or_engine: str | AsyncEngine) -> str:
    """Verify that the target database is strictly an isolated evaluation or test database.

    Raises PermissionError if the target database name is 'ailab'.
    """
    url_str = (
        str(url_or_engine.url) if hasattr(url_or_engine, "url") else str(url_or_engine)
    )
    db_name = url_str.rsplit("/", 1)[-1].split("?")[0].strip()

    if db_name == "ailab":
        raise PermissionError(
            "CRITICAL DATA SAFETY VIOLATION: Synthetic evaluation fixtures must NEVER "
            "be provisioned into the historical production 'ailab' database! "
            "Please configure an isolated test database (e.g. ailab_eval_test)."
        )

    return db_name


@dataclass(slots=True)
class ProvisionedRAGEnvironment:
    """Runtime context and ID mappings for real-stack pgvector evaluation."""

    user_id: UUID
    workspace_map: dict[str, UUID]
    workspace_ref_by_id: dict[UUID, str]
    document_id_map: dict[str, UUID]
    chunk_doc_map: dict[UUID, str]
    chunk_ws_map: dict[UUID, str]
    document_chunks_by_key: dict[str, list[UUID]]
    database_name: str
    total_documents: int
    total_chunks: int
    created_document_ids: list[UUID] = field(default_factory=list)


async def _cleanup_evaluation_user(
    engine: AsyncEngine,
    *,
    user_id: UUID,
) -> None:
    """Delete the temporary evaluation user and all cascading evaluation workspaces/documents."""
    async with AsyncSession(engine, expire_on_commit=False) as session, session.begin():
        # Workspaces created by this evaluation user
        workspaces_result = await session.execute(
            select(Workspace.id).where(Workspace.created_by == user_id)
        )
        ws_ids = list(workspaces_result.scalars().all())

        if ws_ids:
            # Delete memberships
            await session.execute(
                delete(WorkspaceMembership).where(
                    WorkspaceMembership.workspace_id.in_(ws_ids)
                )
            )
            # Delete documents & chunks
            docs_result = await session.execute(
                select(Document.id).where(Document.workspace_id.in_(ws_ids))
            )
            doc_ids = list(docs_result.scalars().all())
            if doc_ids:
                await session.execute(
                    delete(DocumentChunk).where(DocumentChunk.document_id.in_(doc_ids))
                )
                await session.execute(delete(Document).where(Document.id.in_(doc_ids)))
            # Delete workspaces
            await session.execute(delete(Workspace).where(Workspace.id.in_(ws_ids)))

        # Delete user
        await session.execute(delete(User).where(User.id == user_id))


@asynccontextmanager
async def provision_real_rag_fixtures(
    *,
    engine: AsyncEngine,
    manifest: RAGDatasetManifest,
    allow_fixture_writes: bool = True,
) -> AsyncIterator[ProvisionedRAGEnvironment]:
    """Provision deterministic synthetic documents and pgvector chunks into isolated test DB."""
    if not allow_fixture_writes:
        raise PermissionError(
            "Real fixture provisioning requires allow_fixture_writes=True"
        )

    db_name = verify_database_safety(engine)

    user_id = uuid4()
    eval_user = User(
        id=user_id,
        email=f"eval-runner-{user_id.hex[:12]}@eval.invalid",
        full_name="Synthetic RAG Evaluation Runner",
        hashed_password=hash_password(token_urlsafe(32)),
        is_active=False,
    )

    # Determine unique workspace refs needed by dataset
    distinct_ws_refs = sorted(
        {doc.workspace_ref for doc in manifest.documents}
        | {"workspace_alpha", "workspace_beta"}
    )

    workspace_map: dict[str, UUID] = {}
    workspace_ref_by_id: dict[UUID, str] = {}
    workspaces: list[Workspace] = []
    memberships: list[WorkspaceMembership] = []

    for ws_ref in distinct_ws_refs:
        ws_id = uuid4()
        workspace_map[ws_ref] = ws_id
        workspace_ref_by_id[ws_id] = ws_ref
        ws = Workspace(
            id=ws_id,
            name=f"Evaluation Workspace ({ws_ref})",
            slug=f"eval-{ws_ref}-{user_id.hex[:6]}",
            status=WorkspaceStatus.ACTIVE.value,
            created_by=user_id,
        )
        workspaces.append(ws)
        memberships.append(
            WorkspaceMembership(
                workspace_id=ws_id,
                user_id=user_id,
                role=WorkspaceRole.OWNER.value,
            )
        )

    # Chunk and embed all fixture documents using the real production embedding service
    embedding_service = get_embedding_service()
    prepared_docs: list[Document] = []
    prepared_chunks: list[DocumentChunk] = []
    document_id_map: dict[str, UUID] = {}
    chunk_doc_map: dict[UUID, str] = {}
    chunk_ws_map: dict[UUID, str] = {}
    document_chunks_by_key: dict[str, list[UUID]] = {}

    all_chunk_contents: list[str] = []
    chunk_records_meta: list[dict] = []

    for doc in manifest.documents:
        doc_id = uuid4()
        document_id_map[doc.key] = doc_id
        document_chunks_by_key[doc.key] = []
        target_ws_id = workspace_map[doc.workspace_ref]

        db_doc = Document(
            id=doc_id,
            user_id=user_id,
            workspace_id=target_ws_id,
            title=doc.title,
            content=doc.content,
            source_type="text",
            mime_type="text/plain",
            status=DocumentStatus.READY.value,
        )
        prepared_docs.append(db_doc)

        text_chunks = chunk_text(doc.content, chunk_size=1000, overlap=200)
        for ch in text_chunks:
            all_chunk_contents.append(ch.content)
            chunk_records_meta.append(
                {
                    "document_id": doc_id,
                    "document_key": doc.key,
                    "workspace_ref": doc.workspace_ref,
                    "chunk_index": ch.index,
                    "content": ch.content,
                    "char_start": ch.char_start,
                    "char_end": ch.char_end,
                }
            )

    # Generate real dense vector embeddings via sentence-transformers
    if all_chunk_contents:
        embeddings = embedding_service.embed_passages(all_chunk_contents)
    else:
        embeddings = []

    for meta, emb in zip(chunk_records_meta, embeddings, strict=True):
        chunk_id = uuid4()
        db_chunk = DocumentChunk(
            id=chunk_id,
            document_id=meta["document_id"],
            chunk_index=meta["chunk_index"],
            content=meta["content"],
            char_start=meta["char_start"],
            char_end=meta["char_end"],
            embedding=emb,
        )
        prepared_chunks.append(db_chunk)
        chunk_doc_map[chunk_id] = meta["document_key"]
        chunk_ws_map[chunk_id] = meta["workspace_ref"]
        document_chunks_by_key[meta["document_key"]].append(chunk_id)

    # Persist all entities into the isolated test database
    async with AsyncSession(engine, expire_on_commit=False) as session, session.begin():
        session.add(eval_user)
        session.add_all(workspaces)
        session.add_all(memberships)
        await session.flush()

        session.add_all(prepared_docs)
        await session.flush()

        session.add_all(prepared_chunks)
        await session.flush()

    env = ProvisionedRAGEnvironment(
        user_id=user_id,
        workspace_map=workspace_map,
        workspace_ref_by_id=workspace_ref_by_id,
        document_id_map=document_id_map,
        chunk_doc_map=chunk_doc_map,
        chunk_ws_map=chunk_ws_map,
        document_chunks_by_key=document_chunks_by_key,
        database_name=db_name,
        total_documents=len(prepared_docs),
        total_chunks=len(prepared_chunks),
        created_document_ids=[d.id for d in prepared_docs],
    )

    try:
        yield env
    finally:
        await _cleanup_evaluation_user(engine, user_id=user_id)
