"""Unit and integration tests for Model Registry & Capability Discovery (T260027 Slice A)."""

import asyncio
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from httpx import ConnectError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.models.benchmark import AgentBenchmarkCaseResult, AgentBenchmarkRun
from app.models.model_registry import (
    ModelCapabilityStatus,
)
from app.models.user import User
from app.models.workspace import Workspace
from app.services.model_registry_service import ModelRegistryService
from app.services.ollama_discovery import (
    DiscoveredModel,
    OllamaDiscoveryAdapter,
    OllamaDiscoveryError,
)


def test_ollama_discovery_adapter_success():
    """Verify OllamaDiscoveryAdapter normalizes tags, show, and ps data properly."""
    adapter = OllamaDiscoveryAdapter(base_url="http://mock-ollama:11434")

    mock_tags = {
        "models": [
            {
                "name": "qwen3:1.7b",
                "model": "qwen3:1.7b",
                "digest": "sha256:8f68893c",
                "size": 1359293444,
                "details": {
                    "parameter_size": "2.0B",
                    "quantization_level": "Q4_K_M",
                    "family": "qwen3",
                    "format": "gguf",
                },
                "capabilities": ["completion", "tools", "thinking"],
            }
        ]
    }
    mock_ps = {
        "models": [
            {
                "name": "qwen3:1.7b",
                "size_vram": 1024000,
                "expires_at": "2026-10-29T12:00:00Z",
            }
        ]
    }
    mock_show = {
        "model_info": {
            "qwen3.context_length": 40960,
        },
        "capabilities": ["completion", "tools", "thinking"],
    }

    with patch("httpx.AsyncClient.get") as mock_get, patch("httpx.AsyncClient.post") as mock_post:
        async def fake_get(url, **kwargs):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            if "/api/tags" in str(url):
                mock_resp.json.return_value = mock_tags
            elif "/api/ps" in str(url):
                mock_resp.json.return_value = mock_ps
            return mock_resp

        async def fake_post(url, **kwargs):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_show
            return mock_resp

        mock_get.side_effect = fake_get
        mock_post.side_effect = fake_post

        models = asyncio.run(adapter.discover_all_models())
        assert len(models) == 1
        m = models[0]
        assert m.name == "qwen3:1.7b"
        assert m.digest == "sha256:8f68893c"
        assert m.size_bytes == 1359293444
        assert m.parameter_size == "2.0B"
        assert m.quantization_level == "Q4_K_M"
        assert m.context_length == 40960
        assert m.is_loaded is True
        assert "tools" in m.advertised_capabilities
        assert "thinking" in m.advertised_capabilities


def test_ollama_discovery_adapter_offline():
    """Verify OllamaDiscoveryAdapter raises typed OllamaDiscoveryError when offline."""
    adapter = OllamaDiscoveryAdapter(base_url="http://offline-ollama:11434")

    with patch("httpx.AsyncClient.get", side_effect=ConnectError("Connection refused")):
        with pytest.raises(OllamaDiscoveryError) as exc_info:
            asyncio.run(adapter.discover_all_models())
        assert exc_info.value.code == "ollama_offline"


def test_model_registry_service_sync_and_capabilities():
    """Verify ModelRegistryService synchronizes models and marks verified capabilities."""

    async def _run():
        settings = get_settings()
        engine = create_async_engine(settings.database_url, poolclass=NullPool)
        session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

        async with session_factory() as session:
            # 1. Create a fake real benchmark run for qwen3:1.7b
            ws = Workspace(name=f"Bench WS {uuid4().hex[:6]}", slug=f"ws-{uuid4().hex[:8]}")
            session.add(ws)
            await session.flush()

            user = User(
                email=f"bench_tester_{uuid4().hex[:6]}@example.com",
                hashed_password="pw",
                full_name="Bench Tester",
            )
            session.add(user)
            await session.flush()

            bench_run = AgentBenchmarkRun(
                workspace_id=ws.id,
                created_by=user.id,
                name="Real Run",
                dataset_id="agent_reliability_core",
                dataset_version="v1.0",
                execution_mode="real",
                model_name="qwen3:1.7b",
                runtime_config={"model_digest": "sha256:8f68893c"},
                status="completed",
                total_cases=14,
                passed_cases=7,
                failed_cases=7,
                task_success_rate=0.5,
                tool_call_accuracy=0.8,
                citation_f1=0.7,
                security_blocking_rate=0.75,
                benign_overblock_rate=0.0,
                latency_p50_ms=17527.0,
                latency_p95_ms=42440.0,
                latency_mean_ms=20651.0,
            )
            session.add(bench_run)
            await session.flush()

            case_result = AgentBenchmarkCaseResult(
                benchmark_run_id=bench_run.id,
                case_id="BENCH-TOOL-01",
                case_name="Precise read tool selection",
                category="tool_selection_args",
                is_adversarial=False,
                passed=True,
                failure_classification="none",
                score=1.0,
                reason="PASS",
                tool_accuracy=1.0,
                citation_f1=1.0,
                grounding_score=1.0,
                latency_ms=14874.0,
            )
            session.add(case_result)
            await session.commit()

            # 2. Mock discovery adapter returning qwen3:1.7b
            mock_adapter = MagicMock(spec=OllamaDiscoveryAdapter)
            async def fake_discover():
                return [
                    DiscoveredModel(
                        name="qwen3:1.7b",
                        digest="sha256:8f68893c",
                        size_bytes=1359293444,
                        parameter_size="2.0B",
                        quantization_level="Q4_K_M",
                        context_length=40960,
                        family="qwen3",
                        format="gguf",
                        advertised_capabilities=["completion", "tools", "thinking"],
                        is_loaded=True,
                        resource_observations={"size_vram": 1024000},
                        raw_metadata={},
                    )
                ]
            mock_adapter.discover_all_models = fake_discover

            service = ModelRegistryService(discovery_adapter=mock_adapter)
            sync_res = await service.sync_models_from_ollama(session)
            assert "qwen3:1.7b" in sync_res["installed"]
            assert "qwen3:1.7b" in sync_res["loaded"]

            # 3. Verify registry entry and capabilities in database
            entry = await service.get_model_by_name(session, "qwen3:1.7b")
            assert entry is not None
            assert entry.is_installed is True
            assert entry.is_loaded is True
            assert entry.capabilities["chat"] == ModelCapabilityStatus.VERIFIED
            assert entry.capabilities["tools"] == ModelCapabilityStatus.VERIFIED
            assert entry.capabilities["thinking"] == ModelCapabilityStatus.ADVERTISED

            # 4. Verify benchmark profile
            assert len(entry.benchmark_profiles) >= 1
            prof = entry.benchmark_profiles[0]
            assert prof.task_success_rate == 0.5
            assert prof.tool_call_accuracy == 0.8
            assert prof.has_sufficient_sample_size is False
            assert "Preliminary sample" in prof.notes
            assert prof.is_stale is False

        await engine.dispose()

    asyncio.run(_run())


def setup_auth_user(client: TestClient) -> dict[str, str]:
    email = f"model_user_{uuid4().hex[:8]}@example.com"
    pwd = "SecurePassword123!"
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": pwd, "full_name": "Model Tester"},
    )
    assert reg.status_code == 201

    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": pwd},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_model_registry_api_endpoints(client: TestClient):
    """Test REST API endpoints for model listing, single get, toggle active, and benchmarks."""
    headers = setup_auth_user(client)

    # 1. Test GET /api/v1/models (requires auth)
    unauth_resp = client.get("/api/v1/models")
    assert unauth_resp.status_code == 401

    # 2. Mock discover_all_models on the adapter during POST /api/v1/models/refresh
    mock_model_name = f"test-model-{uuid4().hex[:6]}:3b"
    mock_discovered = [
        DiscoveredModel(
            name=mock_model_name,
            digest="sha256:testdigest123",
            size_bytes=2500000000,
            parameter_size="3.0B",
            quantization_level="Q4_K_M",
            context_length=8192,
            family="llama",
            format="gguf",
            advertised_capabilities=["completion", "tools"],
            is_loaded=True,
            resource_observations={"size_vram": 2000000},
            raw_metadata={"license": "apache-2.0"},
        )
    ]
    with patch(
        "app.services.ollama_discovery.OllamaDiscoveryAdapter.discover_all_models",
        return_value=mock_discovered,
    ):
        refresh_res = client.post("/api/v1/models/refresh", headers=headers)
        assert refresh_res.status_code == 200
        ref_data = refresh_res.json()
        assert ref_data["discovered_count"] >= 1

    # 3. Test GET /api/v1/models
    resp = client.get("/api/v1/models", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    item = next(i for i in data["items"] if i["name"] == mock_model_name)
    assert item["digest"] == "sha256:testdigest123"
    assert item["is_active"] is True
    assert item["is_loaded"] is True
    model_id = item["id"]

    # 4. Test GET /api/v1/models/{model_id}
    detail_resp = client.get(f"/api/v1/models/{model_id}", headers=headers)
    assert detail_resp.status_code == 200
    assert detail_resp.json()["name"] == mock_model_name

    # 5. Test PATCH /api/v1/models/{model_id} (toggle active)
    patch_resp = client.patch(
        f"/api/v1/models/{model_id}",
        json={"is_active": False},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["is_active"] is False

    # 6. Test GET /api/v1/models/{model_id}/benchmarks
    bench_resp = client.get(
        f"/api/v1/models/{model_id}/benchmarks",
        headers=headers,
    )
    assert bench_resp.status_code == 200
    assert isinstance(bench_resp.json(), list)
