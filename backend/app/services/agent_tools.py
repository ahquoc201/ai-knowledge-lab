"""Typed tool registry for the governed agent runtime.

Tools are backend-controlled. A tool never receives a workspace or user id from
the model: identity comes exclusively from ``ToolContext`` which the executor
builds from the persisted ``AgentRun``.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_state import ToolSideEffect
from app.core.document_status import DocumentStatus
from app.core.workspace_role import WorkspacePermission
from app.repositories.document import get_document_by_id_and_workspace
from app.repositories.user import get_user_by_id
from app.schemas.document import DocumentCreate
from app.services.document import create_user_document, set_document_status
from app.services.semantic_search import semantic_search

SNIPPET_MAX_CHARS = 400
DOCUMENT_CONTENT_MAX_CHARS = 4000


class ToolError(Exception):
    """Controlled tool failure with a sanitized, model-safe message."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class AuditPolicy:
    ALWAYS = "always"


@dataclass(frozen=True, slots=True)
class ToolContext:
    session: AsyncSession
    workspace_id: UUID
    user_id: UUID
    run_id: UUID
    step_id: UUID
    idempotency_key: str


class ToolInput(BaseModel):
    """Base for tool inputs. Unknown fields (e.g. workspace_id) are rejected."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


ToolHandler = Callable[[ToolContext, Any], Awaitable[BaseModel]]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    input_model: type[ToolInput]
    output_model: type[BaseModel]
    required_permission: WorkspacePermission
    side_effect: ToolSideEffect
    timeout_seconds: float
    handler: ToolHandler
    audit_policy: str = AuditPolicy.ALWAYS
    extract_sources: Callable[[BaseModel], list[dict[str, Any]]] = field(
        default=lambda _output: []
    )
    describe_impact: Callable[[BaseModel], str] = field(default=lambda _i: "")

    @property
    def requires_approval(self) -> bool:
        return self.side_effect == ToolSideEffect.WRITE


# ------------------------------------------------------------- schemas


class SearchInput(ToolInput):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=10)


class SearchHit(BaseModel):
    document_id: UUID
    title: str | None
    chunk_index: int
    snippet: str
    similarity: float


class SearchOutput(BaseModel):
    results: list[SearchHit]


class GetDocumentInput(ToolInput):
    document_id: UUID


class DocumentDetailsOutput(BaseModel):
    document_id: UUID
    title: str
    source_type: str
    status: str
    created_at: datetime
    content: str | None
    content_truncated: bool


class CreateDocumentInput(ToolInput):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=20_000)


class CreateDocumentOutput(BaseModel):
    document_id: UUID
    title: str
    workspace_id: UUID
    status: str


# ------------------------------------------------------------ handlers


async def search_workspace_documents(
    ctx: ToolContext, args: SearchInput
) -> SearchOutput:
    # The tenant filter is applied inside the SQL query (Document.workspace_id).
    results = await semantic_search(
        ctx.session,
        workspace_id=ctx.workspace_id,
        query=args.query,
        limit=args.limit,
    )
    return SearchOutput(
        results=[
            SearchHit(
                document_id=item.chunk.document_id,
                title=item.document_title,
                chunk_index=item.chunk.chunk_index,
                snippet=item.chunk.content[:SNIPPET_MAX_CHARS],
                similarity=round(float(item.similarity), 4),
            )
            for item in results
        ]
    )


async def get_document_details(
    ctx: ToolContext, args: GetDocumentInput
) -> DocumentDetailsOutput:
    document = await get_document_by_id_and_workspace(
        ctx.session,
        document_id=args.document_id,
        workspace_id=ctx.workspace_id,
    )
    if document is None:
        # Identical response for "missing" and "belongs to another workspace".
        raise ToolError("document_not_found", "Document not found in this workspace")

    content = document.content
    truncated = False
    if content is not None and len(content) > DOCUMENT_CONTENT_MAX_CHARS:
        content = content[:DOCUMENT_CONTENT_MAX_CHARS]
        truncated = True

    return DocumentDetailsOutput(
        document_id=document.id,
        title=document.title,
        source_type=document.source_type,
        status=document.status,
        created_at=document.created_at,
        content=content,
        content_truncated=truncated,
    )


async def create_workspace_document(
    ctx: ToolContext, args: CreateDocumentInput
) -> CreateDocumentOutput:
    # Imported lazily to keep the registry importable without Celery wiring.
    from app.tasks.ingestion import process_document_task

    user = await get_user_by_id(ctx.session, ctx.user_id)
    if user is None:
        raise ToolError("principal_not_found", "Initiating user no longer exists")

    document = await create_user_document(
        ctx.session,
        user=user,
        data=DocumentCreate(
            title=args.title,
            content=args.content,
            source_type="text",
            source_name="agent",
        ),
        workspace_id=ctx.workspace_id,
    )

    try:
        process_document_task.delay(str(document.id), str(user.id))
    except Exception:  # noqa: BLE001
        await set_document_status(
            ctx.session,
            document=document,
            status=DocumentStatus.FAILED,
            error_message="Failed to schedule background processing task",
        )

    return CreateDocumentOutput(
        document_id=document.id,
        title=document.title,
        workspace_id=document.workspace_id,
        status=document.status,
    )


# ------------------------------------------------------------- sources


def _search_sources(output: BaseModel) -> list[dict[str, Any]]:
    assert isinstance(output, SearchOutput)
    seen: dict[str, dict[str, Any]] = {}
    for hit in output.results:
        seen.setdefault(
            str(hit.document_id),
            {"document_id": str(hit.document_id), "title": hit.title},
        )
    return list(seen.values())


def _details_sources(output: BaseModel) -> list[dict[str, Any]]:
    assert isinstance(output, DocumentDetailsOutput)
    return [{"document_id": str(output.document_id), "title": output.title}]


def _create_impact(args: BaseModel) -> str:
    assert isinstance(args, CreateDocumentInput)
    return (
        f"Creates 1 new text document ({len(args.content)} characters) in this "
        "workspace and starts indexing it. It becomes searchable and visible to "
        "every member who can read documents."
    )


# ------------------------------------------------------------ registry


class ToolRegistry:
    def __init__(self, specs: list[ToolSpec] | None = None) -> None:
        self._specs: dict[str, ToolSpec] = {}
        for spec in specs or []:
            self.register(spec)

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._specs:
            raise ValueError(f"Tool already registered: {spec.name}")
        self._specs[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    def names(self) -> list[str]:
        return sorted(self._specs)

    def specs(self) -> list[ToolSpec]:
        return [self._specs[name] for name in self.names()]


def build_default_registry() -> ToolRegistry:
    return ToolRegistry(
        [
            ToolSpec(
                name="search_workspace_documents",
                description=(
                    "Semantic search over documents in the CURRENT workspace. "
                    "Returns relevant text snippets with document ids and titles."
                ),
                input_model=SearchInput,
                output_model=SearchOutput,
                required_permission=WorkspacePermission.DOCUMENT_READ,
                side_effect=ToolSideEffect.READ_ONLY,
                timeout_seconds=30.0,
                handler=search_workspace_documents,
                extract_sources=_search_sources,
            ),
            ToolSpec(
                name="get_document_details",
                description=(
                    "Read metadata and (bounded) content of one document in the "
                    "CURRENT workspace by document_id obtained from search results."
                ),
                input_model=GetDocumentInput,
                output_model=DocumentDetailsOutput,
                required_permission=WorkspacePermission.DOCUMENT_READ,
                side_effect=ToolSideEffect.READ_ONLY,
                timeout_seconds=15.0,
                handler=get_document_details,
                extract_sources=_details_sources,
            ),
            ToolSpec(
                name="create_workspace_document",
                description=(
                    "Create a new text document in the CURRENT workspace. This is "
                    "a WRITE action: it only executes after explicit human approval."
                ),
                input_model=CreateDocumentInput,
                output_model=CreateDocumentOutput,
                required_permission=WorkspacePermission.DOCUMENT_CREATE,
                side_effect=ToolSideEffect.WRITE,
                timeout_seconds=30.0,
                handler=create_workspace_document,
                describe_impact=_create_impact,
            ),
        ]
    )
