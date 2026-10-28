"""Unit tests for typed tool contracts and Tool Registry."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.agent_state import ToolSideEffect
from app.core.workspace_role import WorkspacePermission
from app.services.agent_policy import find_forbidden_argument_keys
from app.services.agent_tools import (
    CreateDocumentInput,
    GetDocumentInput,
    SearchInput,
    build_default_registry,
)


def test_default_registry_contents():
    registry = build_default_registry()
    names = registry.names()
    assert "search_workspace_documents" in names
    assert "get_document_details" in names
    assert "create_workspace_document" in names

    search_spec = registry.get("search_workspace_documents")
    assert search_spec is not None
    assert search_spec.side_effect == ToolSideEffect.READ_ONLY
    assert search_spec.required_permission == WorkspacePermission.DOCUMENT_READ
    assert not search_spec.requires_approval

    create_spec = registry.get("create_workspace_document")
    assert create_spec is not None
    assert create_spec.side_effect == ToolSideEffect.WRITE
    assert create_spec.required_permission == WorkspacePermission.DOCUMENT_CREATE
    assert create_spec.requires_approval


def test_tool_input_schema_validation():
    # Valid search input
    search = SearchInput(query="backend architecture", limit=5)
    assert search.query == "backend architecture"
    assert search.limit == 5

    # Invalid search input (empty query or out of bounds limit)
    with pytest.raises(ValidationError):
        SearchInput(query="")
    with pytest.raises(ValidationError):
        SearchInput(query="test", limit=50)

    # Valid get document input
    doc_id = uuid4()
    get_doc = GetDocumentInput(document_id=doc_id)
    assert get_doc.document_id == doc_id

    # Valid create document input
    create_doc = CreateDocumentInput(title="New Note", content="Architecture content")
    assert create_doc.title == "New Note"


def test_tool_inputs_forbid_extra_fields():
    # Attempting to supply arbitrary fields is rejected at schema level
    with pytest.raises(ValidationError):
        SearchInput.model_validate({"query": "test", "extra_field": "injected"})


def test_forbidden_argument_detection():
    # Verify policy detector catches attempts to supply tenant/identity fields
    malicious_args = {
        "query": "hello",
        "workspace_id": str(uuid4()),
        "user_id": str(uuid4()),
        "role": "owner",
        "approved": True,
    }
    forbidden = find_forbidden_argument_keys(malicious_args)
    assert "workspace_id" in forbidden
    assert "user_id" in forbidden
    assert "role" in forbidden
    assert "approved" in forbidden
