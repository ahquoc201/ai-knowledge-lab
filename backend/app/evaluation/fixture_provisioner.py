
"""Provision and clean up an isolated retrieval evaluation corpus."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from secrets import token_urlsafe
from uuid import UUID, uuid4

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import get_settings
from app.core.document_status import DocumentStatus
from app.core.security import hash_password
from app.core.workspace_role import WorkspaceRole, WorkspaceStatus
from app.evaluation.fixture_manifest import (
    RetrievalFixtureManifest,
    build_fixture_golden_dataset,
)
from app.evaluation.models import GoldenDataset
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_membership import WorkspaceMembership
from app.services.document_chunk import build_embedded_document_chunks


@dataclass(frozen=True, slots=True)
class ProvisionedFixture:
    """Resources created for one isolated evaluation run."""

    user_id: UUID
    document_ids: tuple[UUID, ...]
    dataset: GoldenDataset


def _ensure_provisioning_allowed(
    *,
    allow_fixture_writes: bool,
) -> None:
    """Block unapproved fixture writes and production usage."""

    if not allow_fixture_writes:
        raise PermissionError(
            "Fixture database writes require explicit approval"
        )

    if get_settings().app_env not in {"development", "test"}:
        raise PermissionError(
            "Fixture provisioning is limited to development/test"
        )


async def _delete_evaluation_user(
    engine: AsyncEngine,
    *,
    user_id: UUID,
) -> None:
    """Delete only the user created by this evaluation run."""

    async with AsyncSession(engine) as session, session.begin():
        await session.execute(
            delete(Workspace).where(Workspace.created_by == user_id)
        )
        result = await session.execute(
            delete(User)
            .where(User.id == user_id)
            .returning(User.id)
        )

        deleted_id = result.scalar_one_or_none()

        if deleted_id != user_id:
            raise RuntimeError(
                "Evaluation user cleanup could not be confirmed"
            )


@asynccontextmanager
async def provision_retrieval_fixture(
    *,
    engine: AsyncEngine,
    manifest: RetrievalFixtureManifest,
    allow_fixture_writes: bool = False,
) -> AsyncIterator[ProvisionedFixture]:
    """Create an isolated corpus and clean it up on exit."""

    _ensure_provisioning_allowed(
        allow_fixture_writes=allow_fixture_writes,
    )

    user_id = uuid4()
    workspace_id = uuid4()

    evaluation_user = User(
        id=user_id,
        email=f"evaluation-{user_id}@example.invalid",
        full_name="Temporary Retrieval Evaluation",
        hashed_password=hash_password(token_urlsafe(32)),
        is_active=False,
    )

    evaluation_workspace = Workspace(
        id=workspace_id,
        name="Evaluation Workspace",
        slug=f"eval-{user_id}",
        status=WorkspaceStatus.ACTIVE.value,
        created_by=user_id,
    )

    evaluation_membership = WorkspaceMembership(
        workspace_id=workspace_id,
        user_id=user_id,
        role=WorkspaceRole.OWNER.value,
    )

    # Prepare embeddings before opening a write transaction.
    prepared: list[
        tuple[str, Document, list[DocumentChunk]]
    ] = []

    for fixture_document in manifest.documents:
        document_id = uuid4()

        chunks = await build_embedded_document_chunks(
            document_id=document_id,
            content=fixture_document.content,
        )

        if not chunks:
            raise ValueError(
                "Fixture document produced no chunks: "
                f"{fixture_document.key}"
            )

        document = Document(
            id=document_id,
            user_id=user_id,
            workspace_id=workspace_id,
            title=fixture_document.title,
            content=fixture_document.content,
            source_type="text",
            mime_type="text/plain",
            status=DocumentStatus.READY.value,
        )

        prepared.append(
            (fixture_document.key, document, chunks)
        )

    # Persist the complete corpus in one atomic transaction.
    async with AsyncSession(
        engine,
        expire_on_commit=False,
    ) as session, session.begin():
        session.add(evaluation_user)
        session.add(evaluation_workspace)
        session.add(evaluation_membership)
        await session.flush()

        session.add_all(
            document
            for _, document, _ in prepared
        )
        await session.flush()

        for _, _, chunks in prepared:
            session.add_all(chunks)

        await session.flush()

        chunk_ids_by_key = {
            key: [chunk.id for chunk in chunks]
            for key, _, chunks in prepared
        }

        dataset = build_fixture_golden_dataset(
            manifest=manifest,
            chunk_ids_by_document_key=chunk_ids_by_key,
        )

    fixture = ProvisionedFixture(
        user_id=user_id,
        document_ids=tuple(
            document.id
            for _, document, _ in prepared
        ),
        dataset=dataset,
    )

    try:
        yield fixture
    finally:
        await _delete_evaluation_user(
            engine,
            user_id=user_id,
        )
