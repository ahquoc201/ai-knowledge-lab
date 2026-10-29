"""Targeted tests for Slice C: Observability, Metrics & Reliability Dashboard (T260028)."""

from uuid import uuid4

from fastapi.testclient import TestClient


def setup_user_and_workspace(client: TestClient, prefix: str = "slice_c") -> tuple[dict, str, dict]:
    email = f"{prefix}_{uuid4().hex[:8]}@example.com"
    pwd = "SecurePassword123!"
    reg = client.post("/api/v1/auth/register", json={"email": email, "password": pwd, "full_name": f"User {prefix}"})
    assert reg.status_code == 201
    login = client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    ws = client.post(
        "/api/v1/workspaces",
        json={"name": f"Workspace {prefix}", "description": "Observability verification"},
        headers=headers,
    ).json()
    return reg.json(), token, ws


def test_correlation_id_middleware(client: TestClient):
    """Verify X-Request-ID and X-Response-Time-Ms headers are injected by middleware."""
    custom_id = f"req-{uuid4().hex[:12]}"
    res = client.get("/api/v1/health", headers={"X-Request-ID": custom_id})
    assert res.status_code == 200
    assert res.headers.get("X-Request-ID") == custom_id
    assert "X-Response-Time-Ms" in res.headers

    # Auto-generated ID when omitted
    res_auto = client.get("/api/v1/health")
    assert res_auto.status_code == 200
    assert res_auto.headers.get("X-Request-ID") is not None
    assert len(res_auto.headers.get("X-Request-ID")) > 0


def test_readiness_probe_contract(client: TestClient):
    """Readiness probe must distinguish healthy/degraded states and report all critical components."""
    res = client.get("/api/v1/health/ready")
    assert res.status_code in [200, 503]
    body = res.json()
    assert body["status"] in ["healthy", "degraded"]
    assert "postgres" in body["components"]
    assert "redis" in body["components"]
    assert "ollama" in body["components"]
    assert body["components"]["postgres"]["status"] == "up"


def test_reliability_metrics_and_viewer_rbac(client: TestClient):
    """Owner/Admin can access reliability metrics; Viewer is strictly forbidden (HTTP 403)."""
    # 1. Setup owner
    _owner, owner_token, ws = setup_user_and_workspace(client, "obs_owner")
    owner_headers = {"Authorization": f"Bearer {owner_token}", "X-Workspace-Id": ws["id"]}

    # Owner accesses metrics
    metrics_res = client.get("/api/v1/reliability/metrics", headers=owner_headers)
    assert metrics_res.status_code == 200
    metrics = metrics_res.json()
    assert "agent_runtime" in metrics
    assert "inference_governor" in metrics
    assert "rate_limiting" in metrics
    assert metrics["inference_governor"]["max_concurrency"] >= 1

    # 2. Setup a second user (Viewer)
    viewer_email = f"viewer_{uuid4().hex[:8]}@example.com"
    pwd = "SecurePassword123!"
    client.post("/api/v1/auth/register", json={"email": viewer_email, "password": pwd, "full_name": "Viewer User"})
    v_login = client.post("/api/v1/auth/login", json={"email": viewer_email, "password": pwd})
    viewer_token = v_login.json()["access_token"]
    viewer_headers = {"Authorization": f"Bearer {viewer_token}", "X-Workspace-Id": ws["id"]}

    # Owner invites viewer
    inv_res = client.post(
        f"/api/v1/workspaces/{ws['id']}/invitations",
        json={"email": viewer_email, "role": "viewer"},
        headers=owner_headers,
    )
    assert inv_res.status_code == 201
    invite_token = inv_res.json()["invitation_token"]

    # Viewer accepts invitation
    acc_res = client.post(
        "/api/v1/workspaces/invitations/accept",
        json={"token": invite_token},
        headers=viewer_headers,
    )
    assert acc_res.status_code == 200

    # 3. Viewer attempts to get reliability metrics -> MUST BE 403 FORBIDDEN
    forbidden_metrics = client.get("/api/v1/reliability/metrics", headers=viewer_headers)
    assert forbidden_metrics.status_code == 403
    assert "Only workspace OWNER or ADMIN" in forbidden_metrics.json()["detail"]

    # 4. Viewer attempts to trigger stuck recovery -> MUST BE 403 FORBIDDEN
    forbidden_recovery = client.post("/api/v1/reliability/recover-stuck", headers=viewer_headers)
    assert forbidden_recovery.status_code == 403
    assert "Only workspace OWNER or ADMIN" in forbidden_recovery.json()["detail"]

    # 5. Owner triggers stuck recovery -> MUST BE 200 OK
    recovery_res = client.post("/api/v1/reliability/recover-stuck", headers=owner_headers)
    assert recovery_res.status_code == 200
    assert "recovered_count" in recovery_res.json()
