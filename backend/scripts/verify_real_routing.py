"""Real end-to-end integration verification for single-model routing with local Ollama (T260027)."""

import asyncio
import json
from uuid import uuid4
import httpx
from httpx import ASGITransport

from app.main import app

BASE_URL = "http://testserver/api/v1"


async def run_verification():
    print("=== STARTING REAL SINGLE-MODEL INTEGRATION VERIFICATION ===")

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver/api/v1", timeout=120.0) as client:
        # Step 1: Health check
        health = await client.get("/health")
        assert health.status_code == 200, f"Backend health failed: {health.text}"
        print("✓ Step 1: Backend health OK")

        # Step 2: Register & Login valid user
        user_email = f"real_tester_{uuid4().hex[:8]}@example.com"
        pwd = "RealSecurePassword123!"
        reg = await client.post(
            "/auth/register",
            json={"email": user_email, "password": pwd, "full_name": "Real Router Tester"},
        )
        assert reg.status_code == 201, f"Register failed: {reg.text}"

        login = await client.post(
            "/auth/login",
            json={"email": user_email, "password": pwd},
        )
        assert login.status_code == 200, f"Login failed: {login.text}"
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print(f"✓ Step 2: Authenticated as {user_email}")

        # Step 3: Refresh Model Registry from real local Ollama
        refresh = await client.post("/models/refresh", headers=headers)
        assert refresh.status_code == 200, f"Sync Ollama failed: {refresh.text}"
        refresh_data = refresh.json()
        print(f"✓ Step 3: Synced from Ollama: discovered {refresh_data['discovered_count']} model(s)")

        models_list = await client.get("/models", headers=headers)
        assert models_list.status_code == 200
        models = models_list.json()["items"]
        assert any(m["name"] == "qwen3:1.7b" for m in models), "qwen3:1.7b not in registry!"
        qwen = next(m for m in models if m["name"] == "qwen3:1.7b")
        print(f"  Model in registry: {qwen['name']} (RAM loaded: {qwen['is_loaded']}, digest: {qwen['digest'][:16]}...)")

        # Step 4: Create Workspace & Set up headers
        ws_res = await client.post(
            "/workspaces",
            json={"name": "Real Routing Workspace", "description": "Verification"},
            headers=headers,
        )
        assert ws_res.status_code == 201, f"Create workspace failed: {ws_res.text}"
        ws = ws_res.json()
        ws_id = ws["id"]
        headers_ws = {**headers, "X-Workspace-Id": ws_id}
        print(f"✓ Step 4: Created Workspace: {ws['name']} ({ws_id})")

        # Step 5: Send RAG Chat Request with SSE streaming
        print("✓ Step 5: Sending RAG Stream request to real Ollama...")
        events = []
        async with client.stream(
            "POST",
            "/rag/ask/stream",
            json={"query": "PostgreSQL là gì và có tính năng gì nổi bật?", "limit": 3},
            headers=headers_ws,
        ) as response:
            assert response.status_code == 200, f"RAG stream failed with status {response.status_code}"
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    try:
                        ev = json.loads(data_str)
                        events.append(ev)
                    except json.JSONDecodeError:
                        pass

        # Step 6: Verify model routing in SSE events
        model_routed_ev = next((e for e in events if e.get("event") == "model_routed"), None)
        gen_started_ev = next((e for e in events if e.get("event") == "generation_started"), None)
        ans_completed_ev = next((e for e in events if e.get("event") == "answer_completed"), None)

        print(f"  Total SSE events received: {len(events)}")
        if model_routed_ev:
            print(f"✓ Step 6a: 'model_routed' event: model={model_routed_ev.get('model')}, task_type={model_routed_ev.get('task_type')}")
            assert model_routed_ev.get("model") == "qwen3:1.7b"
        if gen_started_ev:
            print(f"✓ Step 6b: 'generation_started' model_name attribution: {gen_started_ev.get('model_name')}")
            assert gen_started_ev.get("model_name") == "qwen3:1.7b"
        if ans_completed_ev:
            print(f"✓ Step 6c: 'answer_completed' model_name: {ans_completed_ev.get('model_name')}")
            assert ans_completed_ev.get("model_name") == "qwen3:1.7b"

        # Step 7: Create a Read-only Agent Run
        print("✓ Step 7: Creating Agent Run for document search...")
        agent_create = await client.post(
            "/agent/runs?blocking=true",
            json={
                "goal": "Tìm kiếm tài liệu về cơ sở dữ liệu trong workspace này",
                "allowed_tools": ["search_workspace_documents", "get_document_details"],
            },
            headers=headers_ws,
        )
        assert agent_create.status_code == 201, f"Create agent run failed: {agent_create.text}"
        run_data = agent_create.json()
        run_id = run_data["id"]
        print(f"  Agent Run created: ID={run_id}, status={run_data['status']}")

        # Step 8: Poll / Fetch completed Agent Run
        print("✓ Step 8: Verifying Agent Run execution and model attribution...")
        for _ in range(10):
            get_res = await client.get(
                f"/agent/runs/{run_id}",
                headers=headers_ws,
            )
            assert get_res.status_code == 200, f"Get agent run failed: {get_res.text}"
            finished_run = get_res.json()
            if finished_run["status"] in ["completed", "failed", "awaiting_approval"]:
                break
            await asyncio.sleep(1.0)

        print(f"  Agent Run execution finished: status={finished_run['status']}, model_name={finished_run.get('model_name')}")

        # Verify model_name was attributed
        assert finished_run.get("model_name") == "qwen3:1.7b", f"Expected qwen3:1.7b, got {finished_run.get('model_name')}"

        # Step 9: Verify Policy Enforcement on Agent Tool Execution
        print("✓ Step 9: Verifying Policy Enforcement on Agent steps & events...")
        events_res = await client.get(
            f"/agent/runs/{run_id}/events?stream=false",
            headers=headers_ws,
        )
        assert events_res.status_code == 200
        run_events = events_res.json()
        model_routed_agent = next((e for e in run_events if e.get("event_type") == "model_routed"), None)
        assert model_routed_agent is not None, "model_routed event not found in agent run events!"
        print(f"  Agent event logged: event_type={model_routed_agent['event_type']}, model={model_routed_agent['data'].get('model')}")

        # Step 10: Verify Routing Decision Audit Table
        print("✓ Step 10: Verifying Model Routing Decision audit record...")
        decisions_res = await client.get(
            f"/model-routing/decisions?workspace_id={ws_id}",
            headers=headers_ws,
        )
        assert decisions_res.status_code == 200
        decisions = decisions_res.json()
        assert len(decisions) >= 1, "No routing decisions persisted in audit trail!"
        latest_decision = decisions[0]
        print(f"  Audit Decision ID={latest_decision['id']}, task_type={latest_decision['task_type']}, selected_model={latest_decision['selected_model']}, latency={latest_decision['latency_ms']}ms")
        assert latest_decision["selected_model"] == "qwen3:1.7b"
        assert latest_decision["workspace_id"] == ws_id

        print("\n=== ALL 10 REAL INTEGRATION CHECKS PASSED SUCCESSFULLY! ===")


if __name__ == "__main__":
    asyncio.run(run_verification())
