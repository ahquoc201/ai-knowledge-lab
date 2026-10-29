"""API tests for Benchmark endpoints (T260026 - Slice C)."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.evaluation.agent_dataset import BenchmarkCategory


@pytest.fixture(autouse=True)
def mock_embedding_query(monkeypatch):
    monkeypatch.setattr(
        "app.services.semantic_search._embed_query",
        lambda text: [0.05] * 384,
    )


def setup_user_and_workspace(client: TestClient, prefix: str = "bench_api"):
    email = f"{prefix}_{uuid4().hex[:8]}@example.com"
    pwd = "SecurePassword123!"
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": pwd, "full_name": f"User {prefix}"},
    )
    assert reg.status_code == 201

    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": pwd},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    ws_res = client.post(
        "/api/v1/workspaces",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": f"{prefix} Workspace", "description": "Benchmark API WS"},
    )
    assert ws_res.status_code == 201
    return reg.json(), token, ws_res.json()


def test_get_benchmark_datasets(client: TestClient):
    _user, token, _ws = setup_user_and_workspace(client, "ds_user")
    res = client.get(
        "/api/v1/benchmarks/datasets",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "datasets" in data
    assert len(data["datasets"]) >= 1
    ds = data["datasets"][0]
    assert ds["id"] == "agent_reliability_core"
    assert len(ds["categories"]) >= 8


def test_trigger_and_list_benchmark_runs(client: TestClient):
    _user, token, ws = setup_user_and_workspace(client, "trig_user")
    headers = {"Authorization": f"Bearer {token}", "X-Workspace-Id": ws["id"]}

    # Trigger run filtered to retrieval_factual (2 fast cases)
    trigger_res = client.post(
        "/api/v1/benchmarks/runs",
        headers=headers,
        json={
            "name": "API Fast Test Run",
            "execution_mode": "simulated",
            "category_filter": BenchmarkCategory.RETRIEVAL_FACTUAL.value,
        },
    )
    assert trigger_res.status_code == 201
    run_data = trigger_res.json()
    assert run_data["id"] is not None
    assert run_data["status"] == "completed"
    assert run_data["total_cases"] == 2
    assert run_data["task_success_rate"] == 1.0
    assert len(run_data["case_results"]) == 2

    # List runs
    list_res = client.get(
        "/api/v1/benchmarks/runs",
        headers=headers,
    )
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["total"] >= 1
    assert any(r["id"] == run_data["id"] for r in list_data["items"])

    # Get run details
    detail_res = client.get(
        f"/api/v1/benchmarks/runs/{run_data['id']}",
        headers=headers,
    )
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["name"] == "API Fast Test Run"
    assert len(detail["case_results"]) == 2


def test_compare_benchmark_runs_api(client: TestClient):
    _user, token, ws = setup_user_and_workspace(client, "cmp_user")
    headers = {"Authorization": f"Bearer {token}", "X-Workspace-Id": ws["id"]}

    # Trigger run 1
    r1 = client.post(
        "/api/v1/benchmarks/runs",
        headers=headers,
        json={
            "name": "Run 1",
            "execution_mode": "simulated",
            "category_filter": BenchmarkCategory.RETRIEVAL_FACTUAL.value,
        },
    ).json()

    # Trigger run 2
    r2 = client.post(
        "/api/v1/benchmarks/runs",
        headers=headers,
        json={
            "name": "Run 2",
            "execution_mode": "simulated",
            "category_filter": BenchmarkCategory.RETRIEVAL_FACTUAL.value,
        },
    ).json()

    # Compare run 2 against run 1
    cmp_res = client.get(
        f"/api/v1/benchmarks/runs/{r2['id']}/compare/{r1['id']}",
        headers=headers,
    )
    assert cmp_res.status_code == 200
    cmp_data = cmp_res.json()
    assert cmp_data["current_run_id"] == r2["id"]
    assert cmp_data["baseline_run_id"] == r1["id"]
    assert "task_success_rate" in cmp_data
    assert "delta" in cmp_data["task_success_rate"]


def test_cross_workspace_benchmark_isolation(client: TestClient):
    _u1, t1, ws1 = setup_user_and_workspace(client, "iso1")
    _u2, t2, ws2 = setup_user_and_workspace(client, "iso2")

    r1 = client.post(
        "/api/v1/benchmarks/runs",
        headers={"Authorization": f"Bearer {t1}", "X-Workspace-Id": ws1["id"]},
        json={
            "name": "WS1 Run",
            "execution_mode": "simulated",
            "category_filter": BenchmarkCategory.RETRIEVAL_FACTUAL.value,
        },
    ).json()

    # User 2 in WS 2 tries to access WS 1's benchmark run -> 404 Not Found
    res = client.get(
        f"/api/v1/benchmarks/runs/{r1['id']}",
        headers={"Authorization": f"Bearer {t2}", "X-Workspace-Id": ws2["id"]},
    )
    assert res.status_code == 404
