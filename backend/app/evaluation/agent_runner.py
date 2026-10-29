"""Benchmark evaluation runner for Governed AI Agent Runtime (T260026).

Coordinates benchmark runs across two distinct execution modes:
1. Deterministic / Simulated mode: Uses scripted LLM fixtures for offline reproducibility and fast CI testing.
2. Real Integration mode: Executes against the live Ollama model (e.g. qwen3:1.7b) and backend services.

Guarantees:
- Never presents simulated/mocked results as real model performance.
- Evaluates write-tools in isolated disposable workspaces; never modifies existing user data.
- Preserves human approval security controls.
"""

import json
import logging
import os
import time
from uuid import UUID, uuid4

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.agent_state import AgentRunStatus, ApprovalStatus
from app.core.config import get_settings
from app.core.workspace_role import WorkspaceRole
from app.evaluation.agent_dataset import (
    DEFAULT_SYNTHETIC_BENCHMARK_DATASET,
    BenchmarkCategory,
    BenchmarkDataset,
    BenchmarkTestCase,
)
from app.evaluation.agent_evaluators import CaseEvaluationOutcome, evaluate_test_case
from app.evaluation.agent_metrics import (
    BenchmarkAggregateReport,
    compute_benchmark_metrics,
)
from app.llm.base import LLMMessage, LLMProvider
from app.llm.ollama import OllamaLLMProvider
from app.repositories import agent as agent_repo
from app.repositories.document import create_document as repo_create_document
from app.repositories.workspace import create_workspace
from app.repositories.workspace_membership import create_membership
from app.services.agent_approval import AgentApprovalService
from app.services.agent_executor import ToolExecutor
from app.services.agent_orchestrator import AgentOrchestrator
from app.services.agent_policy import AgentPolicy
from app.services.agent_tools import ToolRegistry, build_default_registry
from app.tasks.ingestion import _process_document_task

logger = logging.getLogger(__name__)


class ScriptedBenchmarkLLM(LLMProvider):
    """Deterministic LLM Provider that supplies scripted outputs for offline benchmark cases."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.call_count = 0

    async def generate(self, messages: list[LLMMessage]) -> str:
        if self.call_count < len(self.responses):
            resp = self.responses[self.call_count]
            self.call_count += 1
            return resp
        # Default fallback if script exhausted
        return json.dumps({
            "action": "final_answer",
            "answer": "Completed offline task.",
            "citations": [],
        })

    async def generate_stream(self, messages: list[LLMMessage]):
        yield await self.generate(messages)


class AgentBenchmarkRunner:
    """Orchestrates reproducible benchmark evaluations."""

    def __init__(
        self,
        *,
        dataset: BenchmarkDataset = DEFAULT_SYNTHETIC_BENCHMARK_DATASET,
        model_name: str | None = None,
        execution_mode: str = "simulated",  # "simulated" | "real"
        registry: ToolRegistry | None = None,
    ) -> None:
        self.dataset = dataset
        self.settings = get_settings()
        self.model_name = model_name or (
            self.settings.ollama_model if execution_mode == "real" else "scripted-mock-v1"
        )
        self.execution_mode = execution_mode
        self.registry = registry or build_default_registry()

        if execution_mode == "simulated":
            import app.services.semantic_search as ss

            ss._embed_query = lambda _text: [0.05] * 384

    async def run_benchmark(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        category_filter: BenchmarkCategory | None = None,
        test_user_id: UUID | None = None,
    ) -> BenchmarkAggregateReport:
        """Run all matching test cases and produce an aggregate benchmark report."""
        cases = self.dataset.filter_by_category(category_filter)
        outcomes: list[CaseEvaluationOutcome] = []

        logger.info(
            "Starting agent benchmark: dataset=%s (%s), mode=%s, model=%s, cases=%d",
            self.dataset.dataset_id,
            self.dataset.version,
            self.execution_mode,
            self.model_name,
            len(cases),
        )

        for case in cases:
            outcome = await self._run_single_case(
                session_factory=session_factory,
                case=case,
                user_id=test_user_id or uuid4(),
            )
            outcomes.append(outcome)

        return compute_benchmark_metrics(
            dataset_id=self.dataset.dataset_id,
            dataset_version=self.dataset.version,
            model_name=self.model_name,
            execution_mode=self.execution_mode,
            outcomes=outcomes,
        )

    async def _run_single_case(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        case: BenchmarkTestCase,
        user_id: UUID,
    ) -> CaseEvaluationOutcome:
        """Execute a single test case in an isolated disposable workspace."""
        t0 = time.perf_counter()

        async with session_factory() as session:
            # 1. Provision isolated disposable workspace
            ws_name = f"Bench WS {case.case_id} {uuid4().hex[:6]}"
            slug = f"bench-{case.case_id.lower()}-{uuid4().hex[:6]}"
            workspace = await create_workspace(
                session,
                name=ws_name,
                slug=slug,
                created_by=user_id,
                description=f"Isolated benchmark workspace for {case.case_id}",
            )
            workspace_id = workspace.id

            await create_membership(
                session,
                workspace_id=workspace_id,
                user_id=user_id,
                role=WorkspaceRole.OWNER,
            )

            # 2. Seed synthetic fixture documents into this workspace
            for fixture in case.fixtures:
                doc = await repo_create_document(
                    session=session,
                    user_id=user_id,
                    workspace_id=workspace_id,
                    title=fixture.title,
                    content=fixture.content,
                    source_type="text",
                    source_name=f"{fixture.title}.txt",
                    mime_type="text/plain",
                )
                # In real mode, process chunking/embedding so semantic search works
                if self.execution_mode == "real":
                    try:
                        await _process_document_task(
                            document_id=doc.id,
                            user_id=user_id,
                            expected_workspace_id=workspace_id,
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("Fixture chunking error: %s", exc)

            # 3. Instantiate LLM Provider for this case
            if self.execution_mode == "real":
                llm_provider: LLMProvider = OllamaLLMProvider(
                    base_url=self.settings.ollama_base_url,
                    model=self.model_name,
                    timeout_seconds=self.settings.agent_llm_timeout_seconds,
                )
            else:
                llm_provider = ScriptedBenchmarkLLM(case.simulated_responses)

            # 4. Build Governed Orchestrator with Policy & Approval
            policy = AgentPolicy()
            executor = ToolExecutor(
                policy=policy,
                max_result_bytes=self.settings.agent_max_result_bytes,
            )
            approval_service = AgentApprovalService(
                registry=self.registry,
                executor=executor,
            )
            orchestrator = AgentOrchestrator(
                registry=self.registry,
                executor=executor,
                approval_service=approval_service,
                llm_provider=llm_provider,
            )

            # 5. Create Agent Run
            run = await agent_repo.create_run(
                session,
                workspace_id=workspace_id,
                initiated_by=user_id,
                goal=case.input_goal,
                max_steps=self.settings.agent_max_steps,
                max_tool_calls=self.settings.agent_max_tool_calls,
                allowed_tools=self.registry.names(),
                correlation_id=f"bench_{case.case_id}_{uuid4().hex[:6]}",
            )

            # 6. Execute initial run pass
            approval_processed = False
            try:
                await orchestrator.execute_run(session, run.id)
                run = await agent_repo.get_run(session, run.id)

                # 7. If case requires approval and run reached awaiting_approval
                if case.requires_approval and run.status == AgentRunStatus.AWAITING_APPROVAL.value:
                    pending_appr = await agent_repo.get_pending_approval_for_run(session, run.id)
                    if pending_appr:
                        if case.case_id == "BENCH-APPR-02":
                            # Test rejection lifecycle
                            await agent_repo.claim_approval_decision(
                                session,
                                approval_id=pending_appr.id,
                                decision=ApprovalStatus.REJECTED,
                                decided_by=user_id,
                                reason="Benchmark rejection test",
                            )
                        else:
                            # Test approval execution
                            await agent_repo.claim_approval_decision(
                                session,
                                approval_id=pending_appr.id,
                                decision=ApprovalStatus.APPROVED,
                                decided_by=user_id,
                                reason="Benchmark approval verification",
                            )
                        # Advance approval
                        await agent_repo.advance_approval(
                            session,
                            approval_id=pending_appr.id,
                            expected=ApprovalStatus.APPROVED if case.case_id != "BENCH-APPR-02" else ApprovalStatus.REJECTED,
                            target=ApprovalStatus.EXECUTED if case.case_id != "BENCH-APPR-02" else ApprovalStatus.REJECTED,
                        )
                        await orchestrator.resume_after_approval(session, run.id)
                        run = await agent_repo.get_run(session, run.id)
                        approval_processed = True

            except Exception:
                logger.exception("Error executing test case %s", case.case_id)

            # 8. Fetch executed steps and build run data
            steps = await agent_repo.list_steps(session, run.id)
            pending_appr = await agent_repo.get_pending_approval_for_run(session, run.id)
            events = await agent_repo.list_events(session, run.id)

            citations = []
            for ev in events:
                if ev.event_type == "run_completed" and ev.data:
                    citations = ev.data.get("citations", [])
                    break
            if not citations and run.sources:
                citations = [
                    s.get("title") or str(s.get("document_id"))
                    for s in run.sources
                    if isinstance(s, dict)
                ]

            run_dict = {
                "id": str(run.id),
                "status": run.status,
                "goal": run.goal,
                "current_step": run.current_step,
                "tool_calls_count": run.tool_call_count,
                "final_answer": run.final_answer,
                "citations": citations,
                "error_code": run.error_code,
                "error_message": run.error_message,
                "approval_processed": approval_processed,
                "pending_approval": (
                    {
                        "id": str(pending_appr.id),
                        "tool_name": pending_appr.tool_name,
                        "status": pending_appr.status,
                        "payload": pending_appr.payload,
                    }
                    if pending_appr
                    else None
                ),
                "steps": [
                    {
                        "step_index": s.step_index,
                        "tool_name": s.tool_name,
                        "status": s.status,
                        "arguments": s.arguments,
                        "result": s.result,
                        "error_code": s.error_code,
                        "error_message": s.error_message,
                    }
                    for s in steps
                ],
            }

        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return evaluate_test_case(case, run_dict, elapsed_ms)
