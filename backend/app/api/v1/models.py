"""API endpoints for Model Registry & Capability Discovery (T260027)."""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.session import get_session
from app.models.model_registry import ModelRegistryEntry
from app.models.user import User
from app.schemas.model_registry import (
    ModelBenchmarkProfileResponse,
    ModelRefreshResponse,
    ModelRegistryEntryResponse,
    ModelRegistryListResponse,
    ModelUpdateRequest,
)
from app.services.model_registry_service import ModelRegistryService
from app.services.ollama_discovery import OllamaDiscoveryError
from app.services.rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/models", tags=["models"])


def _to_model_entry_response(entry: ModelRegistryEntry) -> ModelRegistryEntryResponse:
    latest_prof = None
    if entry.benchmark_profiles:
        p = entry.benchmark_profiles[0]
        latest_prof = ModelBenchmarkProfileResponse(
            id=p.id,
            model_id=p.model_id,
            model_name=p.model_name,
            model_digest=p.model_digest,
            dataset_id=p.dataset_id,
            dataset_version=p.dataset_version,
            benchmark_run_id=p.benchmark_run_id,
            execution_mode=p.execution_mode,
            task_success_rate=p.task_success_rate,
            tool_call_accuracy=p.tool_call_accuracy,
            citation_reference_f1=p.citation_reference_f1,
            prompt_injection_resistance=p.prompt_injection_resistance,
            tenant_isolation_success=p.tenant_isolation_success,
            policy_blocking_effectiveness=p.policy_blocking_effectiveness,
            actual_data_leakage_rate=p.actual_data_leakage_rate,
            benign_overblock_rate=p.benign_overblock_rate,
            latency_p50_ms=p.latency_p50_ms,
            latency_p95_ms=p.latency_p95_ms,
            latency_mean_ms=p.latency_mean_ms,
            total_cases_evaluated=p.total_cases_evaluated,
            has_sufficient_sample_size=p.has_sufficient_sample_size,
            is_stale=p.is_stale,
            notes=p.notes,
            created_at=p.created_at,
        )

    return ModelRegistryEntryResponse(
        id=entry.id,
        name=entry.name,
        digest=entry.digest,
        provider_type=entry.provider_type,
        is_installed=entry.is_installed,
        is_loaded=entry.is_loaded,
        is_active=entry.is_active,
        parameter_size=entry.parameter_size,
        quantization_level=entry.quantization_level,
        context_length=entry.context_length,
        family=entry.family,
        format=entry.format,
        size_bytes=entry.size_bytes,
        capabilities=entry.capabilities,
        metadata_json=entry.metadata_json,
        resource_observations=entry.resource_observations,
        last_discovered_at=entry.last_discovered_at,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
        latest_profile=latest_prof,
    )


@router.get("", response_model=ModelRegistryListResponse)
async def list_registered_models(
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    only_installed: Annotated[bool, Query()] = False,
    only_active: Annotated[bool, Query()] = False,
) -> ModelRegistryListResponse:
    """List all registered models, their capabilities, and load states."""
    service = ModelRegistryService()

    # If registry is currently empty in DB, perform an initial sync attempt
    all_models = await service.list_models(
        session, only_installed=only_installed, only_active=only_active
    )
    if not all_models:
        try:
            await service.sync_models_from_ollama(session)
            all_models = await service.list_models(
                session, only_installed=only_installed, only_active=only_active
            )
        except (OllamaDiscoveryError, OSError) as e:
            logger.warning("Initial background model sync failed: %s", e)

    items = [_to_model_entry_response(m) for m in all_models]
    installed_count = sum(1 for m in all_models if m.is_installed)
    loaded_count = sum(1 for m in all_models if m.is_loaded)
    active_count = sum(1 for m in all_models if m.is_active)

    return ModelRegistryListResponse(
        items=items,
        total=len(items),
        installed_count=installed_count,
        loaded_count=loaded_count,
        active_count=active_count,
    )


@router.post("/refresh", response_model=ModelRefreshResponse)
async def refresh_models(
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ModelRefreshResponse:
    """Discover installed models from Ollama and reconcile with registry."""
    settings = get_settings()
    limiter = get_rate_limiter()
    limiter.enforce(str(current_user.id), settings.rate_limit_model_refresh_per_user_per_minute, 60, "model_refresh")

    service = ModelRegistryService()
    try:
        sync_result = await service.sync_models_from_ollama(session)
    except OllamaDiscoveryError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Ollama discovery error: {e.message}",
        ) from e

    installed = sync_result.get("installed", [])
    loaded = sync_result.get("loaded", [])
    uninstalled = sync_result.get("uninstalled", [])

    return ModelRefreshResponse(
        discovered_count=len(installed),
        installed_models=installed,
        loaded_models=loaded,
        uninstalled_models=uninstalled,
        message=f"Discovered {len(installed)} installed model(s) from Ollama. Currently loaded in memory: {len(loaded)}.",
    )


@router.get("/{model_id}", response_model=ModelRegistryEntryResponse)
async def get_model_entry(
    model_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ModelRegistryEntryResponse:
    """Get single model metadata, capabilities and latest benchmark profile."""
    service = ModelRegistryService()
    entry = await service.get_model(session, model_id)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found in registry",
        )
    return _to_model_entry_response(entry)


@router.patch("/{model_id}", response_model=ModelRegistryEntryResponse)
async def update_model_entry(
    model_id: UUID,
    payload: ModelUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ModelRegistryEntryResponse:
    """Update model active status (admin only toggle)."""
    service = ModelRegistryService()
    entry = await service.update_active_status(session, model_id, payload.is_active)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found in registry",
        )
    return _to_model_entry_response(entry)


@router.get("/{model_id}/benchmarks", response_model=list[ModelBenchmarkProfileResponse])
async def get_model_benchmark_profiles(
    model_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[ModelBenchmarkProfileResponse]:
    """Get historical and aggregated benchmark evaluation profiles for this model."""
    service = ModelRegistryService()
    entry = await service.get_model(session, model_id)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found in registry",
        )

    return [
        ModelBenchmarkProfileResponse(
            id=p.id,
            model_id=p.model_id,
            model_name=p.model_name,
            model_digest=p.model_digest,
            dataset_id=p.dataset_id,
            dataset_version=p.dataset_version,
            benchmark_run_id=p.benchmark_run_id,
            execution_mode=p.execution_mode,
            task_success_rate=p.task_success_rate,
            tool_call_accuracy=p.tool_call_accuracy,
            citation_reference_f1=p.citation_reference_f1,
            prompt_injection_resistance=p.prompt_injection_resistance,
            tenant_isolation_success=p.tenant_isolation_success,
            policy_blocking_effectiveness=p.policy_blocking_effectiveness,
            actual_data_leakage_rate=p.actual_data_leakage_rate,
            benign_overblock_rate=p.benign_overblock_rate,
            latency_p50_ms=p.latency_p50_ms,
            latency_p95_ms=p.latency_p95_ms,
            latency_mean_ms=p.latency_mean_ms,
            total_cases_evaluated=p.total_cases_evaluated,
            has_sufficient_sample_size=p.has_sufficient_sample_size,
            is_stale=p.is_stale,
            notes=p.notes,
            created_at=p.created_at,
        )
        for p in entry.benchmark_profiles
    ]
