"""Unit and integration tests for Model Routing, Security Gates and Observability (T260027 Slice B)."""

import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.models.model_registry import (
    ModelBenchmarkProfile,
    ModelCapabilityStatus,
    ModelRegistryEntry,
)
from app.models.model_routing import ModelRoutingPolicy, TaskType
from app.services.model_router import ModelRouter
from app.services.task_classifier import TaskClassifier


def test_task_classifier_seven_types() -> None:
    """Validate deterministic classification across all 7 task types."""
    classifier = TaskClassifier()

    # 1. Simple Chat
    t1 = classifier.classify("Xin chào bạn, hôm nay thời tiết thế nào?")
    assert t1 == TaskType.SIMPLE_CHAT

    # 2. RAG Factual QA
    t2 = classifier.classify("Chính sách hoàn tiền là gì?", has_retrieved_context=True, context_document_count=1)
    assert t2 == TaskType.RAG_FACTUAL_QA

    # 3. RAG Multi Document Synthesis
    t3 = classifier.classify("Tổng hợp thông tin doanh thu từ các báo cáo", has_retrieved_context=True, context_document_count=4)
    assert t3 == TaskType.RAG_MULTI_DOCUMENT_SYNTHESIS

    # 4. Structured Extraction
    t4 = classifier.classify("Trích xuất thông tin theo json format sau:")
    assert t4 == TaskType.STRUCTURED_EXTRACTION

    # 5. Agent Tool Selection
    t5 = classifier.classify("Tìm kiếm tài liệu tài chính", requires_tools=True)
    assert t5 == TaskType.AGENT_TOOL_SELECTION

    # 6. Agent Multi Step Workflow
    t6 = classifier.classify("Bước 1: Tìm kiếm tài liệu, Bước 2: Phân tích, Bước 3: Xuất báo cáo", requires_tools=True)
    assert t6 == TaskType.AGENT_MULTI_STEP_WORKFLOW

    # 7. Agent Write Proposal
    t7 = classifier.classify("Tạo tài liệu mới trong workspace", requires_tools=True, is_write_operation=True)
    assert t7 == TaskType.AGENT_WRITE_PROPOSAL


def test_security_hard_gates_exclusion() -> None:
    """Security hard gates: models with data leakage, tenant violations, or missing allowlist must be excluded."""
    router = ModelRouter()
    policy = ModelRoutingPolicy(
        name="Security Policy",
        default_model="safe-model:latest",
        allowed_models=["safe-model:latest", "leaky-model:latest", "violator-model:latest"],
        fallback_models=["safe-model:latest"],
        task_rules={},
    )

    # 1. Safe model
    safe_entry = ModelRegistryEntry(
        name="safe-model:latest",
        digest="safe123",
        is_installed=True,
        is_active=True,
        capabilities={"chat": ModelCapabilityStatus.VERIFIED},
    )
    safe_eval = router.evaluate_candidate(safe_entry, TaskType.SIMPLE_CHAT, policy)
    assert safe_eval.eligible is True
    assert safe_eval.security_passed is True

    # 2. Leaky model (data leakage rate > 0)
    leaky_entry = ModelRegistryEntry(
        name="leaky-model:latest",
        digest="leaky123",
        is_installed=True,
        is_active=True,
        capabilities={"chat": ModelCapabilityStatus.VERIFIED},
    )
    leaky_profile = ModelBenchmarkProfile(
        model_id=leaky_entry.id,
        model_name="leaky-model:latest",
        model_digest="leaky123",
        dataset_id="test",
        dataset_version="v1",
        execution_mode="MOCK",
        actual_data_leakage_rate=0.08,  # > 0.0 FAIL
        tenant_isolation_success=1.0,
    )
    leaky_entry.benchmark_profiles = [leaky_profile]
    leaky_eval = router.evaluate_candidate(leaky_entry, TaskType.SIMPLE_CHAT, policy)
    assert leaky_eval.eligible is False
    assert leaky_eval.security_passed is False
    assert "data leakage" in leaky_eval.reason

    # 3. Tenant boundary violator
    violator_entry = ModelRegistryEntry(
        name="violator-model:latest",
        digest="viol123",
        is_installed=True,
        is_active=True,
        capabilities={"chat": ModelCapabilityStatus.VERIFIED},
    )
    violator_profile = ModelBenchmarkProfile(
        model_id=violator_entry.id,
        model_name="violator-model:latest",
        model_digest="viol123",
        dataset_id="test",
        dataset_version="v1",
        execution_mode="MOCK",
        actual_data_leakage_rate=0.0,
        tenant_isolation_success=0.85,  # < 1.0 FAIL
    )
    violator_entry.benchmark_profiles = [violator_profile]
    viol_eval = router.evaluate_candidate(violator_entry, TaskType.SIMPLE_CHAT, policy)
    assert viol_eval.eligible is False
    assert viol_eval.security_passed is False
    assert "tenant isolation" in viol_eval.reason

    # 4. Unlisted model (not in allowlist)
    unlisted_entry = ModelRegistryEntry(
        name="unauthorized-model:latest",
        digest="unauth123",
        is_installed=True,
        is_active=True,
        capabilities={"chat": ModelCapabilityStatus.VERIFIED},
    )
    unauth_eval = router.evaluate_candidate(unlisted_entry, TaskType.SIMPLE_CHAT, policy)
    assert unauth_eval.eligible is False
    assert unauth_eval.security_passed is False
    assert "allowlist" in unauth_eval.reason


def test_capability_verification_gate() -> None:
    """Tool-dependent tasks require verified or advertised tools capability."""
    router = ModelRouter()
    policy = ModelRoutingPolicy(
        name="Capability Policy",
        default_model="chat-only:latest",
        allowed_models=["chat-only:latest", "tool-capable:latest"],
        fallback_models=[],
        task_rules={},
    )

    chat_only = ModelRegistryEntry(
        name="chat-only:latest",
        digest="chat123",
        is_installed=True,
        is_active=True,
        capabilities={"chat": ModelCapabilityStatus.VERIFIED, "tools": ModelCapabilityStatus.UNKNOWN},
    )
    eval_tool_task = router.evaluate_candidate(chat_only, TaskType.AGENT_TOOL_SELECTION, policy)
    assert eval_tool_task.eligible is False
    assert "tools is unknown or unsupported" in eval_tool_task.reason


def test_bounded_fallback_execution() -> None:
    """Fallback executes secondary eligible model when primary encounters an operational failure."""

    async def _run() -> None:
        settings = get_settings()
        engine = create_async_engine(settings.database_url, poolclass=NullPool)
        session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

        async with session_factory() as session:
            router = ModelRouter()

            primary_called = False
            secondary_called = False

            async def mock_execute(model_name: str) -> str:
                nonlocal primary_called, secondary_called
                if model_name == "failing-model":
                    primary_called = True
                    raise RuntimeError("Ollama connection reset or context overflow")
                if model_name == "backup-model":
                    secondary_called = True
                    return "Execution successful on backup"
                raise ValueError(f"Unknown model {model_name}")

            policy = ModelRoutingPolicy(
                name="Fallback Test Policy",
                default_model="failing-model",
                allowed_models=["failing-model", "backup-model"],
                fallback_models=["backup-model"],
                max_fallback_attempts=2,
                task_rules={},
            )
            session.add(policy)
            await session.commit()

            from app.services.model_router import (
                CandidateEvaluation,
                RoutingDecisionResult,
            )

            mock_decision = RoutingDecisionResult(
                selected_model="failing-model",
                task_type=TaskType.SIMPLE_CHAT,
                policy_id=policy.id,
                policy_version="v1.0",
                candidate_evaluations=[
                    CandidateEvaluation("failing-model", True, 0.9, "Score 0.9"),
                    CandidateEvaluation("backup-model", True, 0.8, "Score 0.8"),
                ],
                selection_reason="Highest initial score",
                fallback_chain=["backup-model"],
            )
            router.select_model = AsyncMock(return_value=mock_decision)  # type: ignore

            result, routing = await router.execute_with_fallback(
                session=session,
                task_type=TaskType.SIMPLE_CHAT,
                execute_fn=mock_execute,
            )

            assert primary_called is True
            assert secondary_called is True
            assert result == "Execution successful on backup"
            assert routing.selected_model == "backup-model"
            assert routing.is_fallback is True
            assert "Recovered via fallback attempt #1" in routing.selection_reason

    asyncio.run(_run())


def setup_auth_user(client: TestClient) -> dict[str, str]:
    email = f"router_user_{uuid4().hex[:8]}@example.com"
    pwd = "SecurePassword123!"
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": pwd, "full_name": "Router Tester"},
    )
    assert reg.status_code == 201

    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": pwd},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_model_routing_apis(client: TestClient) -> None:
    """Test policy read, update permissions, preview, and decision audit trail APIs."""
    headers = setup_auth_user(client)

    # Create workspace through API
    ws_res = client.post(
        "/api/v1/workspaces",
        json={"name": "Routing Test Workspace", "description": "Routing test"},
        headers=headers,
    )
    assert ws_res.status_code == 201
    ws = ws_res.json()
    ws_id = ws["id"]

    # 1. GET Policy
    res_policy = client.get(
        f"/api/v1/model-routing/policies?workspace_id={ws_id}",
        headers=headers,
    )
    assert res_policy.status_code == 200
    policy_data = res_policy.json()
    assert "default_model" in policy_data
    policy_id = policy_data["id"]

    # 2. PUT Policy Update
    res_update = client.put(
        f"/api/v1/model-routing/policies/{policy_id}",
        json={
            "name": "Updated Workspace Routing Policy",
            "max_fallback_attempts": 3,
        },
        headers=headers,
    )
    assert res_update.status_code == 200
    assert res_update.json()["max_fallback_attempts"] == 3

    # 3. POST Preview
    res_preview = client.post(
        "/api/v1/model-routing/preview",
        json={
            "workspace_id": str(ws_id),
            "prompt": "Trích xuất thông tin khách hàng từ JSON",
            "requires_tools": False,
        },
        headers=headers,
    )
    assert res_preview.status_code == 200
    preview_data = res_preview.json()
    assert preview_data["task_type"] == TaskType.STRUCTURED_EXTRACTION
    assert "selected_model" in preview_data
    assert "candidate_evaluations" in preview_data

    # 4. GET Decisions Audit
    res_decisions = client.get(
        f"/api/v1/model-routing/decisions?workspace_id={ws_id}",
        headers=headers,
    )
    assert res_decisions.status_code == 200
    assert isinstance(res_decisions.json(), list)
