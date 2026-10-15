from uuid import uuid4

from fastapi.testclient import TestClient


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


def test_auto_provision_personal_workspace_on_registration(client: TestClient):
    _user, token = register_and_login(client, "personal")

    res = client.get(
        "/api/v1/workspaces",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    workspaces = res.json()
    assert len(workspaces) >= 1

    personal_ws = next((w for w in workspaces if "personal" in w["slug"]), None)
    assert personal_ws is not None
    assert personal_ws["current_user_role"] == "owner"


def test_create_and_get_workspace(client: TestClient):
    _, token = register_and_login(client, "creator")

    # Create workspace
    create_res = client.post(
        "/api/v1/workspaces",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Engineering Lab", "description": "Tech space"},
    )
    assert create_res.status_code == 201
    data = create_res.json()
    assert data["name"] == "Engineering Lab"
    assert data["current_user_role"] == "owner"
    ws_id = data["id"]

    # Get workspace
    get_res = client.get(
        f"/api/v1/workspaces/{ws_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_res.status_code == 200
    assert get_res.json()["name"] == "Engineering Lab"

    # Update workspace
    patch_res = client.patch(
        f"/api/v1/workspaces/{ws_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Engineering Lab V2"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["name"] == "Engineering Lab V2"


def test_non_member_cannot_access_workspace(client: TestClient):
    _, owner_token = register_and_login(client, "owner")
    _, stranger_token = register_and_login(client, "stranger")

    create_res = client.post(
        "/api/v1/workspaces",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"name": "Confidential Lab"},
    )
    assert create_res.status_code == 201
    ws_id = create_res.json()["id"]

    # Stranger tries to read
    stranger_res = client.get(
        f"/api/v1/workspaces/{ws_id}",
        headers={"Authorization": f"Bearer {stranger_token}"},
    )
    assert stranger_res.status_code == 403


def test_invitation_lifecycle_and_role_escalation_blocked(client: TestClient):
    _, owner_token = register_and_login(client, "teamowner")
    member_user, member_token = register_and_login(client, "colleague")

    create_res = client.post(
        "/api/v1/workspaces",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"name": "Shared Lab"},
    )
    assert create_res.status_code == 201
    ws_id = create_res.json()["id"]

    # 1. Owner invites member as viewer
    invite_res = client.post(
        f"/api/v1/workspaces/{ws_id}/invitations",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email": member_user["email"], "role": "viewer"},
    )
    assert invite_res.status_code == 201
    token = invite_res.json()["invitation_token"]

    # 2. Member accepts invitation
    accept_res = client.post(
        "/api/v1/workspaces/invitations/accept",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"token": token},
    )
    assert accept_res.status_code == 200
    assert accept_res.json()["role"] == "viewer"

    # 3. List members
    members_res = client.get(
        f"/api/v1/workspaces/{ws_id}/members",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert members_res.status_code == 200
    emails = [m["email"] for m in members_res.json()]
    assert member_user["email"] in emails

    # 4. Privilege escalation: VIEWER cannot change member roles
    escalate_res = client.patch(
        f"/api/v1/workspaces/{ws_id}/members/{member_user['id']}",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"role": "admin"},
    )
    assert escalate_res.status_code == 403

    # 5. Owner promotes member to editor
    promote_res = client.patch(
        f"/api/v1/workspaces/{ws_id}/members/{member_user['id']}",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"role": "editor"},
    )
    assert promote_res.status_code == 200
    assert promote_res.json()["role"] == "editor"


def test_last_owner_protection(client: TestClient):
    owner_user, owner_token = register_and_login(client, "solowner")

    create_res = client.post(
        "/api/v1/workspaces",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"name": "Solo Lab"},
    )
    assert create_res.status_code == 201
    ws_id = create_res.json()["id"]

    # Cannot downgrade self
    downgrade_res = client.patch(
        f"/api/v1/workspaces/{ws_id}/members/{owner_user['id']}",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"role": "editor"},
    )
    assert downgrade_res.status_code in {400, 403}

    # Cannot leave workspace if last owner
    leave_res = client.post(
        f"/api/v1/workspaces/{ws_id}/leave",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert leave_res.status_code == 400
    assert "last owner" in leave_res.json()["detail"].lower()
