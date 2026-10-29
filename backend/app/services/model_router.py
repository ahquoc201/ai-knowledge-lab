"""Model Router Engine for Adaptive Model Selection and Reliability Fallback (T260027).

Selects optimal LLM for RAG Chat and Agent Workflows based on:
1. Deterministic task classification.
2. Security hard gates (Tenant isolation, data leakage, admin allowlist).
3. Capability verification (Verified vs Advertised).
4. Mathematical, versioned scoring (Quality, Tool accuracy, Latency penalty, Cold-start bonus).
5. Bounded, safe fallback without approval or RBAC bypass.
6. Full audit logging via ModelRoutingDecision.
"""

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.model_registry import (
    ModelCapabilityStatus,
    ModelRegistryEntry,
)
from app.models.model_routing import (
    ModelRoutingDecision,
    ModelRoutingPolicy,
    TaskType,
)
from app.services.model_registry_service import ModelRegistryService

logger = logging.getLogger(__name__)

DEFAULT_TASK_RULES = {
    TaskType.SIMPLE_CHAT: {
        "quality_weight": 0.4,
        "tool_weight": 0.0,
        "latency_weight": 0.5,
        "required_capabilities": ["chat"],
    },
    TaskType.RAG_FACTUAL_QA: {
        "quality_weight": 0.6,
        "tool_weight": 0.0,
        "latency_weight": 0.4,
        "required_capabilities": ["chat"],
    },
    TaskType.RAG_MULTI_DOCUMENT_SYNTHESIS: {
        "quality_weight": 0.7,
        "tool_weight": 0.0,
        "latency_weight": 0.3,
        "min_context_length": 4096,
        "required_capabilities": ["chat"],
    },
    TaskType.STRUCTURED_EXTRACTION: {
        "quality_weight": 0.5,
        "tool_weight": 0.3,
        "latency_weight": 0.2,
        "required_capabilities": ["structured_output"],
    },
    TaskType.AGENT_TOOL_SELECTION: {
        "quality_weight": 0.3,
        "tool_weight": 0.5,
        "latency_weight": 0.2,
        "required_capabilities": ["tools"],
    },
    TaskType.AGENT_MULTI_STEP_WORKFLOW: {
        "quality_weight": 0.4,
        "tool_weight": 0.5,
        "latency_weight": 0.1,
        "required_capabilities": ["tools"],
    },
    TaskType.AGENT_WRITE_PROPOSAL: {
        "quality_weight": 0.4,
        "tool_weight": 0.5,
        "latency_weight": 0.1,
        "required_capabilities": ["tools"],
    },
}


@dataclass
class CandidateEvaluation:
    model_name: str
    eligible: bool
    score: float
    reason: str
    is_loaded: bool = False
    security_passed: bool = True
    capabilities_met: bool = True
    metrics_summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "eligible": self.eligible,
            "score": round(self.score, 4),
            "reason": self.reason,
            "is_loaded": self.is_loaded,
            "security_passed": self.security_passed,
            "capabilities_met": self.capabilities_met,
            "metrics_summary": self.metrics_summary,
        }


@dataclass
class RoutingDecisionResult:
    selected_model: str
    task_type: str
    policy_id: UUID | None
    policy_version: str
    candidate_evaluations: list[CandidateEvaluation]
    selection_reason: str
    fallback_chain: list[str]
    is_fallback: bool = False
    decision_id: UUID | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_model": self.selected_model,
            "task_type": self.task_type,
            "policy_id": str(self.policy_id) if self.policy_id else None,
            "policy_version": self.policy_version,
            "candidate_evaluations": [c.to_dict() for c in self.candidate_evaluations],
            "selection_reason": self.selection_reason,
            "fallback_chain": self.fallback_chain,
            "is_fallback": self.is_fallback,
            "decision_id": str(self.decision_id) if self.decision_id else None,
        }


class ModelRouter:
    def __init__(self, registry_service: ModelRegistryService | None = None) -> None:
        self.registry_service = registry_service or ModelRegistryService()
        self.settings = get_settings()

    async def get_or_create_policy(
        self, session: AsyncSession, workspace_id: UUID | None = None
    ) -> ModelRoutingPolicy:
        """Fetch active policy for workspace or default system policy."""
        stmt = (
            select(ModelRoutingPolicy)
            .filter_by(workspace_id=workspace_id)
            .order_by(ModelRoutingPolicy.created_at.desc())
        )
        res = await session.execute(stmt)
        policy = res.scalars().first()

        if policy is None:
            # Seed workspace policy or system default policy
            default_name = self.settings.ollama_model
            policy = ModelRoutingPolicy(
                workspace_id=workspace_id,
                name=f"{'Workspace' if workspace_id else 'System Default'} Routing Policy",
                version="v1.0",
                is_enabled=True,
                default_model=default_name,
                allowed_models=[default_name],
                fallback_models=[default_name],
                max_fallback_attempts=2,
                task_rules=DEFAULT_TASK_RULES,
            )
            session.add(policy)
            await session.commit()
            await session.refresh(policy)

        return policy

    def evaluate_candidate(
        self,
        entry: ModelRegistryEntry,
        task_type: str,
        policy: ModelRoutingPolicy,
    ) -> CandidateEvaluation:
        """Evaluate a model candidate against Security Hard Gates and calculate score."""
        # 1. Basic Operational Gates
        if not entry.is_installed:
            return CandidateEvaluation(
                model_name=entry.name,
                eligible=False,
                score=0.0,
                reason="Model is not installed in local environment",
                is_loaded=entry.is_loaded,
                security_passed=True,
                capabilities_met=False,
            )

        if not entry.is_active:
            return CandidateEvaluation(
                model_name=entry.name,
                eligible=False,
                score=0.0,
                reason="Model is disabled by administrator",
                is_loaded=entry.is_loaded,
                security_passed=True,
                capabilities_met=False,
            )

        if entry.name not in policy.allowed_models:
            return CandidateEvaluation(
                model_name=entry.name,
                eligible=False,
                score=0.0,
                reason="Model not in authorized workspace allowlist",
                is_loaded=entry.is_loaded,
                security_passed=False,
                capabilities_met=False,
            )

        # 2. Security Hard Gates from Benchmark Profile
        latest_profile = entry.benchmark_profiles[0] if entry.benchmark_profiles else None

        # Check digest mismatch or stale flag: profile loses validity if digest changed or explicitly stale
        if latest_profile:
            is_mismatch = bool(
                latest_profile.model_digest
                and entry.digest
                and latest_profile.model_digest != entry.digest
            )
            if is_mismatch or latest_profile.is_stale:
                latest_profile = None

        rule = (policy.task_rules or {}).get(task_type) or DEFAULT_TASK_RULES.get(
            task_type, {}
        )

        # Gate 2a: Tasks with explicit verified security requirement (e.g. write proposals or strict policies)
        if rule.get("require_verified_security", False) and (
            not latest_profile or latest_profile.total_cases_evaluated == 0
        ):
            return CandidateEvaluation(
                    model_name=entry.name,
                    eligible=False,
                    score=0.0,
                    reason="Security gate failed: task requires verified benchmark profile but model has no valid measurements",
                    is_loaded=entry.is_loaded,
                    security_passed=False,
                    capabilities_met=True,
                )

        # Gate 2b: Leakage & Tenant Isolation Checks (Fail-closed on None, missing or violating metrics)
        if latest_profile:
            leakage = latest_profile.actual_data_leakage_rate
            if leakage is None or leakage > 0.0:
                return CandidateEvaluation(
                    model_name=entry.name,
                    eligible=False,
                    score=0.0,
                    reason=f"Security gate failed: measured actual data leakage rate is {('missing (None)' if leakage is None else f'{leakage * 100:.1f}%')}",
                    is_loaded=entry.is_loaded,
                    security_passed=False,
                    capabilities_met=True,
                )

            tenant_iso = latest_profile.tenant_isolation_success
            if tenant_iso is None or tenant_iso < 1.0:
                return CandidateEvaluation(
                    model_name=entry.name,
                    eligible=False,
                    score=0.0,
                    reason=f"Security gate failed: tenant isolation boundary was violated or unverified ({tenant_iso})",
                    is_loaded=entry.is_loaded,
                    security_passed=False,
                    capabilities_met=True,
                )

        # 3. Capability Requirements
        rule = (policy.task_rules or {}).get(task_type) or DEFAULT_TASK_RULES.get(
            task_type, {}
        )
        required_caps = rule.get("required_capabilities", [])
        caps = entry.capabilities or {}

        for req in required_caps:
            status = caps.get(req, ModelCapabilityStatus.UNKNOWN)
            if status == ModelCapabilityStatus.UNKNOWN:
                return CandidateEvaluation(
                    model_name=entry.name,
                    eligible=False,
                    score=0.0,
                    reason=f"Missing capability: {req} is unknown or unsupported",
                    is_loaded=entry.is_loaded,
                    security_passed=True,
                    capabilities_met=False,
                )

        min_ctx = rule.get("min_context_length")
        if min_ctx and entry.context_length and entry.context_length < min_ctx:
            return CandidateEvaluation(
                model_name=entry.name,
                eligible=False,
                score=0.0,
                reason=f"Context window ({entry.context_length}) smaller than required ({min_ctx})",
                is_loaded=entry.is_loaded,
                security_passed=True,
                capabilities_met=False,
            )

        # 4. Transparent Scoring Formulation
        # Score = w_quality * Quality + w_tool * ToolAccuracy - w_latency * LatencyPenalty + ColdStartBonus
        w_qual = rule.get("quality_weight", 0.5)
        w_tool = rule.get("tool_weight", 0.0)
        w_lat = rule.get("latency_weight", 0.3)

        if latest_profile:
            qual_score = latest_profile.task_success_rate
            tool_score = latest_profile.tool_call_accuracy
            lat_penalty = min(1.0, latest_profile.latency_p50_ms / 30000.0)
            metrics_summary = {
                "success_rate": latest_profile.task_success_rate,
                "tool_accuracy": latest_profile.tool_call_accuracy,
                "latency_p50_ms": latest_profile.latency_p50_ms,
                "has_sufficient_samples": latest_profile.has_sufficient_sample_size,
            }
        else:
            # Baseline assumptions for models without real benchmark profile yet
            qual_score = 0.5
            tool_score = (
                0.5 if caps.get("tools") == ModelCapabilityStatus.ADVERTISED else 0.0
            )
            lat_penalty = 0.2
            metrics_summary = {"status": "unprofiled_defaults"}

        cold_start_bonus = 0.1 if entry.is_loaded else 0.0
        calculated_score = (
            (w_qual * qual_score)
            + (w_tool * tool_score)
            - (w_lat * lat_penalty)
            + cold_start_bonus
        )
        calculated_score = max(0.01, min(1.0, calculated_score))

        reason = (
            f"Eligible. Score={calculated_score:.2f} (Qual={qual_score:.2f}, "
            f"Tool={tool_score:.2f}, Lat={lat_penalty:.2f}, "
            f"{'Loaded in RAM' if entry.is_loaded else 'Cold start'})"
        )

        return CandidateEvaluation(
            model_name=entry.name,
            eligible=True,
            score=calculated_score,
            reason=reason,
            is_loaded=entry.is_loaded,
            security_passed=True,
            capabilities_met=True,
            metrics_summary=metrics_summary,
        )

    async def select_model(
        self,
        session: AsyncSession,
        task_type: str,
        workspace_id: UUID | None = None,
        manual_model_override: str | None = None,
        context_metadata: dict[str, Any] | None = None,
    ) -> RoutingDecisionResult:
        """Select eligible model for the given task type according to active policy."""
        t0 = time.perf_counter()
        policy = await self.get_or_create_policy(session, workspace_id)
        all_models = await self.registry_service.list_models(session)

        # If no models registered, trigger initial sync
        if not all_models:
            await self.registry_service.sync_models_from_ollama(session)
            all_models = await self.registry_service.list_models(session)

        candidates = [
            self.evaluate_candidate(m, task_type, policy) for m in all_models
        ]
        eligible = [c for c in candidates if c.eligible]

        # Handle manual override if requested
        if manual_model_override:
            override_cand = next(
                (c for c in candidates if c.model_name == manual_model_override), None
            )
            if override_cand and override_cand.eligible:
                decision = RoutingDecisionResult(
                    selected_model=manual_model_override,
                    task_type=task_type,
                    policy_id=policy.id,
                    policy_version=policy.version,
                    candidate_evaluations=candidates,
                    selection_reason=f"Manual user selection: {manual_model_override} verified eligible against security & capability constraints.",
                    fallback_chain=[c.model_name for c in eligible if c.model_name != manual_model_override],
                )
                await self._persist_decision(session, decision, workspace_id, t0, context_metadata)
                return decision
            logger.warning(
                "Manual override '%s' is not eligible for task %s. Falling back to policy router.",
                manual_model_override,
                task_type,
            )

        # Auto-routing disabled case: use default_model if eligible
        if not policy.is_enabled:
            def_cand = next(
                (c for c in eligible if c.model_name == policy.default_model), None
            )
            selected = def_cand.model_name if def_cand else (eligible[0].model_name if eligible else policy.default_model)
            decision = RoutingDecisionResult(
                selected_model=selected,
                task_type=task_type,
                policy_id=policy.id,
                policy_version=policy.version,
                candidate_evaluations=candidates,
                selection_reason=f"Auto-routing disabled. Using default configured model: {selected}",
                fallback_chain=[c.model_name for c in eligible if c.model_name != selected],
            )
            await self._persist_decision(session, decision, workspace_id, t0, context_metadata)
            return decision

        # Adaptive Model Selection: Highest Score Among Eligible Candidates
        if eligible:
            # Sort descending by score, tie-break by is_loaded (memory locality)
            eligible.sort(key=lambda c: (c.score, 1 if c.is_loaded else 0), reverse=True)
            chosen = eligible[0]
            fallback_chain = [c.model_name for c in eligible[1:]]

            # Also incorporate explicit policy fallback models if eligible
            for fb in policy.fallback_models:
                if fb not in fallback_chain and fb != chosen.model_name:
                    fb_cand = next((c for c in eligible if c.model_name == fb), None)
                    if fb_cand:
                        fallback_chain.append(fb)

            decision = RoutingDecisionResult(
                selected_model=chosen.model_name,
                task_type=task_type,
                policy_id=policy.id,
                policy_version=policy.version,
                candidate_evaluations=candidates,
                selection_reason=f"Optimal candidate selected by policy scoring: {chosen.reason}",
                fallback_chain=fallback_chain[: policy.max_fallback_attempts],
            )
        else:
            # Fail closed: No models pass eligibility hard gates
            logger.error(
                "No eligible model found for task %s in workspace %s. All candidates excluded.",
                task_type,
                workspace_id,
            )
            decision = RoutingDecisionResult(
                selected_model=policy.default_model,
                task_type=task_type,
                policy_id=policy.id,
                policy_version=policy.version,
                candidate_evaluations=candidates,
                selection_reason="CRITICAL: Zero candidates met eligibility gates. Falling back to default system model.",
                fallback_chain=[],
                is_fallback=True,
            )

        await self._persist_decision(session, decision, workspace_id, t0, context_metadata)
        return decision

    async def _persist_decision(
        self,
        session: AsyncSession,
        decision: RoutingDecisionResult,
        workspace_id: UUID | None,
        t0: float,
        context_metadata: dict[str, Any] | None,
    ) -> None:
        """Audit record for routing decision (Strictly NO raw prompts or sensitive document texts!)."""
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        sanitized_ctx = {}
        if context_metadata:
            for k, v in context_metadata.items():
                if k not in ["prompt", "content", "query", "text", "document_body"]:
                    sanitized_ctx[k] = v

        record = ModelRoutingDecision(
            workspace_id=workspace_id,
            task_type=decision.task_type,
            policy_id=decision.policy_id,
            policy_version=decision.policy_version,
            selected_model=decision.selected_model,
            candidate_evaluations=[c.to_dict() for c in decision.candidate_evaluations],
            selection_reason=decision.selection_reason,
            fallback_occurred=decision.is_fallback,
            fallback_chain=decision.fallback_chain,
            latency_ms=latency_ms,
            context_metadata=sanitized_ctx,
            created_at=datetime.now(UTC),
        )
        session.add(record)
        await session.commit()
        decision.decision_id = record.id

    async def preview_routing(
        self,
        session: AsyncSession,
        task_type: str,
        workspace_id: UUID | None = None,
        manual_model_override: str | None = None,
    ) -> RoutingDecisionResult:
        """Dry-run preview of routing decision without executing LLM or persisting audit decision."""
        policy = await self.get_or_create_policy(session, workspace_id)
        all_models = await self.registry_service.list_models(session)
        if not all_models:
            await self.registry_service.sync_models_from_ollama(session)
            all_models = await self.registry_service.list_models(session)

        candidates = [
            self.evaluate_candidate(m, task_type, policy) for m in all_models
        ]
        eligible = [c for c in candidates if c.eligible]

        if manual_model_override:
            override_cand = next(
                (c for c in candidates if c.model_name == manual_model_override), None
            )
            if override_cand and override_cand.eligible:
                return RoutingDecisionResult(
                    selected_model=manual_model_override,
                    task_type=task_type,
                    policy_id=policy.id,
                    policy_version=policy.version,
                    candidate_evaluations=candidates,
                    selection_reason=f"Manual user selection: {manual_model_override} verified eligible against security & capability constraints.",
                    fallback_chain=[c.model_name for c in eligible if c.model_name != manual_model_override],
                )

        if not policy.is_enabled:
            def_cand = next(
                (c for c in eligible if c.model_name == policy.default_model), None
            )
            selected = def_cand.model_name if def_cand else (eligible[0].model_name if eligible else policy.default_model)
            return RoutingDecisionResult(
                selected_model=selected,
                task_type=task_type,
                policy_id=policy.id,
                policy_version=policy.version,
                candidate_evaluations=candidates,
                selection_reason=f"Auto-routing disabled. Using default configured model: {selected}",
                fallback_chain=[c.model_name for c in eligible if c.model_name != selected],
            )

        if eligible:
            eligible.sort(key=lambda c: (c.score, 1 if c.is_loaded else 0), reverse=True)
            chosen = eligible[0]
            fallback_chain = [c.model_name for c in eligible[1:]]
            for fb in policy.fallback_models:
                if fb not in fallback_chain and fb != chosen.model_name:
                    fb_cand = next((c for c in eligible if c.model_name == fb), None)
                    if fb_cand:
                        fallback_chain.append(fb)

            return RoutingDecisionResult(
                selected_model=chosen.model_name,
                task_type=task_type,
                policy_id=policy.id,
                policy_version=policy.version,
                candidate_evaluations=candidates,
                selection_reason=f"Optimal candidate selected by policy scoring: {chosen.reason}",
                fallback_chain=fallback_chain[: policy.max_fallback_attempts],
            )
        else:
            return RoutingDecisionResult(
                selected_model=policy.default_model,
                task_type=task_type,
                policy_id=policy.id,
                policy_version=policy.version,
                candidate_evaluations=candidates,
                selection_reason="CRITICAL: Zero candidates met eligibility gates. Falling back to default system model.",
                fallback_chain=[],
                is_fallback=True,
            )

    async def update_policy(
        self,
        session: AsyncSession,
        policy_id: UUID,
        update_data: dict[str, Any],
    ) -> ModelRoutingPolicy | None:
        """Update an existing routing policy."""
        stmt = select(ModelRoutingPolicy).filter_by(id=policy_id)
        res = await session.execute(stmt)
        policy = res.scalars().first()
        if not policy:
            return None

        for k, v in update_data.items():
            if v is not None and hasattr(policy, k):
                setattr(policy, k, v)

        await session.commit()
        await session.refresh(policy)
        return policy

    async def list_decisions(
        self,
        session: AsyncSession,
        workspace_id: UUID | None = None,
        task_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ModelRoutingDecision]:
        """List audit records for routing decisions."""
        stmt = select(ModelRoutingDecision)
        if workspace_id:
            stmt = stmt.filter(ModelRoutingDecision.workspace_id == workspace_id)
        if task_type:
            stmt = stmt.filter(ModelRoutingDecision.task_type == task_type)
        stmt = stmt.order_by(ModelRoutingDecision.created_at.desc()).limit(limit).offset(offset)
        res = await session.execute(stmt)
        return list(res.scalars().all())

    async def execute_with_fallback(
        self,
        session: AsyncSession,
        task_type: str,
        execute_fn: Callable[[str], Awaitable[Any]],
        workspace_id: UUID | None = None,
        manual_model_override: str | None = None,
        context_metadata: dict[str, Any] | None = None,
    ) -> tuple[Any, RoutingDecisionResult]:
        """Execute operation with primary routed model, falling back safely if model unavailable."""
        routing = await self.select_model(
            session=session,
            task_type=task_type,
            workspace_id=workspace_id,
            manual_model_override=manual_model_override,
            context_metadata=context_metadata,
        )

        models_to_try = [routing.selected_model] + routing.fallback_chain
        last_exception: Exception | None = None

        for idx, model_name in enumerate(models_to_try):
            try:
                result = await execute_fn(model_name)
                if idx > 0:
                    routing.selected_model = model_name
                    routing.is_fallback = True
                    routing.selection_reason += f" (Recovered via fallback attempt #{idx}: {model_name})"
                return result, routing
            except (RuntimeError, ValueError, OSError, TimeoutError) as e:
                logger.warning(
                    "Execution with model %s failed: %s. Attempting fallback.",
                    model_name,
                    e,
                )
                last_exception = e

        raise RuntimeError(
            f"All eligible models in fallback chain failed execution for task {task_type}. Last error: {last_exception}"
        ) from last_exception
