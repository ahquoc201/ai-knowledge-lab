import io
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.workspace_role import WorkspaceRole
from app.llm.base import LLMMessage, LLMProvider
from app.llm.ollama import get_ollama_llm_provider
from app.services.rag_prompt import INSUFFICIENT_CONTEXT_ANSWER
from app.tasks.ingestion import _process_document_task


class MockOllamaLLM(LLMProvider):
    async def generate(self, messages: list[LLMMessage]) -> str:
        return "Tài liệu cho biết: Thông tin bảo mật [Source 1]."

    async def generate_stream(self, messages: list[LLMMessage]):
        yield "Tài liệu cho biết: Thông tin bảo mật [Source 1]."


def register_and_login(client: TestClient, email_prefix: str = "user") -> tuple[dict, str]:
    email = f"{email_prefix}-{uuid4()}@example.com"
    password = "TestPassword123!"

    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": f"User {email_prefix}",
        },
    )
    assert reg_res.status_code == 201
    user_data = reg_res.json()

    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]

    return user_data, token


def create_custom_workspace(client: TestClient, token: str, name: str) -> dict:
    res = client.post(
        "/api/v1/workspaces",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name, "description": f"Description for {name}"},
    )
    assert res.status_code == 201
    return res.json()


# =========================================================================
# Scenario 1: Cross-tenant Document Access
# =========================================================================
def test_scenario_1_cross_tenant_document_access(client: TestClient):
    """User B cannot view or delete documents belonging to Workspace A."""
    _user_a, token_a = register_and_login(client, "alice")
    _user_b, token_b = register_and_login(client, "bob")

    ws_a = create_custom_workspace(client, token_a, "Alice Workspace")
    ws_b = create_custom_workspace(client, token_b, "Bob Workspace")

    # Alice creates a document in Workspace A
    doc_res = client.post(
        "/api/v1/documents",
        headers={
            "Authorization": f"Bearer {token_a}",
            "X-Workspace-Id": ws_a["id"],
        },
        json={
            "title": "Alice Confidential Strategy",
            "content": "Secret revenue projection 2027.",
            "source_type": "text",
        },
    )
    assert doc_res.status_code == 201
    doc_id = doc_res.json()["id"]

    # Bob attempts to GET Alice's document using his own workspace context -> 404
    bob_get_res = client.get(
        f"/api/v1/documents/{doc_id}",
        headers={
            "Authorization": f"Bearer {token_b}",
            "X-Workspace-Id": ws_b["id"],
        },
    )
    assert bob_get_res.status_code == 404

    # Bob attempts to GET Alice's document by forging X-Workspace-Id header -> 403 Forbidden
    bob_forged_res = client.get(
        f"/api/v1/documents/{doc_id}",
        headers={
            "Authorization": f"Bearer {token_b}",
            "X-Workspace-Id": ws_a["id"],
        },
    )
    assert bob_forged_res.status_code == 403

    # Bob attempts to DELETE Alice's document -> 404 or 403
    bob_del_res = client.delete(
        f"/api/v1/documents/{doc_id}",
        headers={
            "Authorization": f"Bearer {token_b}",
            "X-Workspace-Id": ws_b["id"],
        },
    )
    assert bob_del_res.status_code == 404

    # Verify Alice's document is still intact
    alice_check = client.get(
        f"/api/v1/documents/{doc_id}",
        headers={
            "Authorization": f"Bearer {token_a}",
            "X-Workspace-Id": ws_a["id"],
        },
    )
    assert alice_check.status_code == 200
    assert alice_check.json()["title"] == "Alice Confidential Strategy"


# =========================================================================
# Scenario 2: Cross-tenant Vector Leakage
# =========================================================================
def test_scenario_2_cross_tenant_vector_leakage(client: TestClient):
    """User in Workspace B asking about unique secret in Workspace A receives refusal, 0 chunks leaked."""
    _user_a, token_a = register_and_login(client, "alice-rag")
    _user_b, token_b = register_and_login(client, "bob-rag")

    ws_a = create_custom_workspace(client, token_a, "Alice Team")
    ws_b = create_custom_workspace(client, token_b, "Bob Team")

    # Ingest document with unique codename into Workspace A
    client.post(
        "/api/v1/documents",
        headers={
            "Authorization": f"Bearer {token_a}",
            "X-Workspace-Id": ws_a["id"],
        },
        json={
            "title": "Codename Supernova",
            "content": "Secret code PROJECT-SUPERNOVA-X9 is classified under tier 1 clearance.",
            "source_type": "text",
        },
    )

    client.app.dependency_overrides[get_ollama_llm_provider] = lambda: MockOllamaLLM()
    try:
        # Bob in Workspace B asks about PROJECT-SUPERNOVA-X9
        rag_res = client.post(
            "/api/v1/rag/ask",
            headers={
                "Authorization": f"Bearer {token_b}",
                "X-Workspace-Id": ws_b["id"],
            },
            json={
                "query": "Thông tin về PROJECT-SUPERNOVA-X9 là gì?",
            },
        )
        assert rag_res.status_code == 200
        data = rag_res.json()

        # Strict RAG isolation: must refuse and have 0 sources
        assert data["answer"] == INSUFFICIENT_CONTEXT_ANSWER
        assert len(data["sources"]) == 0
    finally:
        client.app.dependency_overrides.pop(get_ollama_llm_provider, None)


# =========================================================================
# Scenario 3: Cross-tenant Conversation Hijacking
# =========================================================================
def test_scenario_3_cross_tenant_conversation_hijacking(client: TestClient):
    """User B cannot read or inject messages into User A's conversation."""
    _user_a, token_a = register_and_login(client, "alice-conv")
    _user_b, token_b = register_and_login(client, "bob-conv")

    ws_a = create_custom_workspace(client, token_a, "Workspace Alpha")
    ws_b = create_custom_workspace(client, token_b, "Workspace Beta")

    # Alice creates a conversation in Workspace A
    conv_res = client.post(
        "/api/v1/conversations",
        headers={
            "Authorization": f"Bearer {token_a}",
            "X-Workspace-Id": ws_a["id"],
        },
        json={"title": "Alpha Internal Planning"},
    )
    assert conv_res.status_code == 201
    conv_id = conv_res.json()["id"]

    # Bob attempts to GET Alice's conversation -> 404
    bob_get_res = client.get(
        f"/api/v1/conversations/{conv_id}",
        headers={
            "Authorization": f"Bearer {token_b}",
            "X-Workspace-Id": ws_b["id"],
        },
    )
    assert bob_get_res.status_code == 404

    # Bob attempts to inject a message into Alice's conversation via /rag/ask
    client.app.dependency_overrides[get_ollama_llm_provider] = lambda: MockOllamaLLM()
    try:
        bob_inject_res = client.post(
            "/api/v1/rag/ask",
            headers={
                "Authorization": f"Bearer {token_b}",
                "X-Workspace-Id": ws_b["id"],
            },
            json={
                "conversation_id": conv_id,
                "query": "Injected malicious message",
            },
        )
        assert bob_inject_res.status_code == 404
    finally:
        client.app.dependency_overrides.pop(get_ollama_llm_provider, None)


# =========================================================================
# Scenario 4: Role-based Ingestion Restriction
# =========================================================================
def test_scenario_4_role_based_ingestion_restriction(client: TestClient):
    """A member with VIEWER role cannot create or upload documents."""
    _owner, owner_token = register_and_login(client, "owner-ingest")
    user_viewer, viewer_token = register_and_login(client, "viewer-ingest")

    ws = create_custom_workspace(client, owner_token, "Restricted Ingestion WS")
    ws_id = ws["id"]

    # Invite viewer
    invite_res = client.post(
        f"/api/v1/workspaces/{ws_id}/invitations",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "email": user_viewer["email"],
            "role": WorkspaceRole.VIEWER.value,
        },
    )
    assert invite_res.status_code == 201
    invite_token = invite_res.json()["invitation_token"]

    # Viewer accepts invitation
    accept_res = client.post(
        "/api/v1/workspaces/invitations/accept",
        headers={"Authorization": f"Bearer {viewer_token}"},
        json={"token": invite_token},
    )
    assert accept_res.status_code == 200

    # Viewer tries to create text document -> 403 Forbidden
    create_res = client.post(
        "/api/v1/documents",
        headers={
            "Authorization": f"Bearer {viewer_token}",
            "X-Workspace-Id": ws_id,
        },
        json={
            "title": "Viewer Unauthorized Document",
            "content": "This should be blocked.",
            "source_type": "text",
        },
    )
    assert create_res.status_code == 403
    assert "document.create" in create_res.json()["detail"]

    # Viewer tries to upload file document -> 403 Forbidden
    file_bytes = io.BytesIO(b"Unauthorized file content")
    upload_res = client.post(
        "/api/v1/documents/upload",
        headers={
            "Authorization": f"Bearer {viewer_token}",
            "X-Workspace-Id": ws_id,
        },
        files={"file": ("unauthorized.txt", file_bytes, "text/plain")},
    )
    assert upload_res.status_code == 403
    assert "document.create" in upload_res.json()["detail"]


# =========================================================================
# Scenario 5: Role-based Deletion Restriction
# =========================================================================
def test_scenario_5_role_based_deletion_restriction(client: TestClient):
    """A member with VIEWER role cannot delete documents."""
    _owner, owner_token = register_and_login(client, "owner-del")
    user_viewer, viewer_token = register_and_login(client, "viewer-del")

    ws = create_custom_workspace(client, owner_token, "Deletion Protected WS")
    ws_id = ws["id"]

    # Owner creates document
    doc_res = client.post(
        "/api/v1/documents",
        headers={
            "Authorization": f"Bearer {owner_token}",
            "X-Workspace-Id": ws_id,
        },
        json={
            "title": "Protected Knowledge",
            "content": "Mission critical policy.",
            "source_type": "text",
        },
    )
    assert doc_res.status_code == 201
    doc_id = doc_res.json()["id"]

    # Invite viewer and accept
    invite_res = client.post(
        f"/api/v1/workspaces/{ws_id}/invitations",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email": user_viewer["email"], "role": WorkspaceRole.VIEWER.value},
    )
    client.post(
        "/api/v1/workspaces/invitations/accept",
        headers={"Authorization": f"Bearer {viewer_token}"},
        json={"token": invite_res.json()["invitation_token"]},
    )

    # Viewer attempts DELETE -> 403 Forbidden
    del_res = client.delete(
        f"/api/v1/documents/{doc_id}",
        headers={
            "Authorization": f"Bearer {viewer_token}",
            "X-Workspace-Id": ws_id,
        },
    )
    assert del_res.status_code == 403
    assert "document.delete" in del_res.json()["detail"]

    # Document still exists
    verify_res = client.get(
        f"/api/v1/documents/{doc_id}",
        headers={
            "Authorization": f"Bearer {owner_token}",
            "X-Workspace-Id": ws_id,
        },
    )
    assert verify_res.status_code == 200


# =========================================================================
# Scenario 6: Role Escalation Prevention
# =========================================================================
def test_scenario_6_role_escalation_prevention(client: TestClient):
    """An EDITOR cannot escalate their own role or promote others to ADMIN/OWNER."""
    _owner, owner_token = register_and_login(client, "owner-esc")
    user_editor, editor_token = register_and_login(client, "editor-esc")

    ws = create_custom_workspace(client, owner_token, "Privilege Guard WS")
    ws_id = ws["id"]

    # Invite editor and accept
    invite_res = client.post(
        f"/api/v1/workspaces/{ws_id}/invitations",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email": user_editor["email"], "role": WorkspaceRole.EDITOR.value},
    )
    client.post(
        "/api/v1/workspaces/invitations/accept",
        headers={"Authorization": f"Bearer {editor_token}"},
        json={"token": invite_res.json()["invitation_token"]},
    )

    # Editor tries to change their own role to admin -> 403 Forbidden
    escalate_res = client.patch(
        f"/api/v1/workspaces/{ws_id}/members/{user_editor['id']}",
        headers={
            "Authorization": f"Bearer {editor_token}",
            "X-Workspace-Id": ws_id,
        },
        json={"role": WorkspaceRole.ADMIN.value},
    )
    assert escalate_res.status_code == 403


# =========================================================================
# Scenario 7: Last Owner Protection
# =========================================================================
def test_scenario_7_last_owner_protection(client: TestClient):
    """The sole owner cannot demote themselves or leave the workspace."""
    user_owner, owner_token = register_and_login(client, "sole-owner")

    ws = create_custom_workspace(client, owner_token, "Indestructible WS")
    ws_id = ws["id"]

    # Sole owner tries to demote self to editor -> 400 Bad Request
    demote_res = client.patch(
        f"/api/v1/workspaces/{ws_id}/members/{user_owner['id']}",
        headers={
            "Authorization": f"Bearer {owner_token}",
            "X-Workspace-Id": ws_id,
        },
        json={"role": WorkspaceRole.EDITOR.value},
    )
    assert demote_res.status_code == 400
    assert "only owner" in demote_res.json()["detail"].lower()

    # Sole owner tries to remove self -> 400 Bad Request
    remove_res = client.delete(
        f"/api/v1/workspaces/{ws_id}/members/{user_owner['id']}",
        headers={
            "Authorization": f"Bearer {owner_token}",
            "X-Workspace-Id": ws_id,
        },
    )
    assert remove_res.status_code == 400
    assert "only owner" in remove_res.json()["detail"].lower()


# =========================================================================
# Scenario 8: Celery Cross-tenant Ingestion Safety
# =========================================================================
def test_scenario_8_celery_cross_tenant_ingestion_safety(client: TestClient):
    """Worker detects and blocks document processing when expected workspace mismatches database."""
    import asyncio
    from uuid import UUID

    _owner_a, token_a = register_and_login(client, "alice-celery")
    ws_a = create_custom_workspace(client, token_a, "Celery Workspace A")

    # Create document in Workspace A
    doc_res = client.post(
        "/api/v1/documents",
        headers={
            "Authorization": f"Bearer {token_a}",
            "X-Workspace-Id": ws_a["id"],
        },
        json={
            "title": "Celery Target Doc",
            "content": "Valid body text.",
            "source_type": "text",
        },
    )
    doc_id = doc_res.json()["id"]

    fake_different_workspace_id = uuid4()

    # Call _process_document_task with mismatched expected_workspace_id
    with pytest.raises(ValueError, match="Cross-tenant ingestion attempt blocked"):
        asyncio.run(
            _process_document_task(
                document_id=UUID(doc_id),
                user_id=UUID(_owner_a["id"]),
                expected_workspace_id=fake_different_workspace_id,
            )
        )



# =========================================================================
# Scenario 9: Audit Trail Integrity
# =========================================================================
def test_scenario_9_audit_trail_integrity(client: TestClient):
    """Sensitive security operations are recorded in the workspace audit trail; viewers cannot view it."""
    _owner, owner_token = register_and_login(client, "owner-audit")
    user_viewer, viewer_token = register_and_login(client, "viewer-audit")

    ws = create_custom_workspace(client, owner_token, "Audit Trail WS")
    ws_id = ws["id"]

    # Owner creates a document (generates audit event)
    client.post(
        "/api/v1/documents",
        headers={
            "Authorization": f"Bearer {owner_token}",
            "X-Workspace-Id": ws_id,
        },
        json={
            "title": "Audited Document",
            "content": "Audited content.",
            "source_type": "text",
        },
    )

    # Owner invites viewer (generates audit event)
    invite_res = client.post(
        f"/api/v1/workspaces/{ws_id}/invitations",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email": user_viewer["email"], "role": WorkspaceRole.VIEWER.value},
    )
    client.post(
        "/api/v1/workspaces/invitations/accept",
        headers={"Authorization": f"Bearer {viewer_token}"},
        json={"token": invite_res.json()["invitation_token"]},
    )

    # Owner queries audit events
    audit_res = client.get(
        f"/api/v1/workspaces/{ws_id}/audit-events",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert audit_res.status_code == 200
    events = audit_res.json()["items"]
    assert len(events) >= 2
    actions = {e["action"] for e in events}
    assert "document.create" in actions or "member.invite" in actions

    # Viewer attempts to read audit events -> 403 Forbidden
    viewer_audit_res = client.get(
        f"/api/v1/workspaces/{ws_id}/audit-events",
        headers={
            "Authorization": f"Bearer {viewer_token}",
            "X-Workspace-Id": ws_id,
        },
    )
    assert viewer_audit_res.status_code == 403
    assert "audit.read" in viewer_audit_res.json()["detail"]
