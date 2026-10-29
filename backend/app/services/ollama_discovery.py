"""Ollama Model Discovery Adapter (T260027).

Fetches installed, running, and metadata information directly from Ollama REST APIs:
- GET /api/tags: Installed models and digests.
- GET /api/ps: Currently loaded models in memory/VRAM.
- POST /api/show: Deep architecture, parameters, template, context length, families.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredModel:
    name: str
    digest: str
    size_bytes: int | None
    parameter_size: str | None
    quantization_level: str | None
    context_length: int | None
    family: str | None
    format: str | None
    advertised_capabilities: list[str] = field(default_factory=list)
    is_loaded: bool = False
    resource_observations: dict[str, Any] = field(default_factory=dict)
    raw_metadata: dict[str, Any] = field(default_factory=dict)


class OllamaDiscoveryError(Exception):
    def __init__(self, message: str, code: str = "ollama_discovery_failed") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class OllamaDiscoveryAdapter:
    def __init__(self, base_url: str | None = None, timeout_seconds: float = 10.0) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def check_health(self) -> bool:
        """Ping Ollama endpoint to verify connectivity."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                res = await client.get(f"{self.base_url}/api/tags")
                return res.status_code == 200
        except (httpx.HTTPError, OSError):
            return False

    async def list_running_models(self) -> dict[str, dict[str, Any]]:
        """Query GET /api/ps to inspect models currently loaded into memory/VRAM."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                res = await client.get(f"{self.base_url}/api/ps")
                if res.status_code != 200:
                    return {}
                data = res.json()
                models = data.get("models", [])
                running: dict[str, dict[str, Any]] = {}
                for m in models:
                    name = m.get("name") or m.get("model")
                    if name:
                        running[name] = {
                            "size_vram": m.get("size_vram"),
                            "size": m.get("size"),
                            "expires_at": m.get("expires_at"),
                            "digest": m.get("digest"),
                        }
                return running
        except (httpx.HTTPError, OSError) as e:
            logger.warning("Failed to fetch running models from Ollama /api/ps: %s", e)
            return {}

    async def get_model_details(self, model_name: str) -> dict[str, Any]:
        """Query POST /api/show for a specific model."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                res = await client.post(
                    f"{self.base_url}/api/show",
                    json={"name": model_name},
                )
                if res.status_code == 200:
                    return res.json()
                logger.warning(
                    "Ollama /api/show for %s returned status %s",
                    model_name,
                    res.status_code,
                )
                return {}
        except (httpx.HTTPError, OSError) as e:
            logger.warning("Failed to fetch model details from /api/show for %s: %s", model_name, e)
            return {}

    async def discover_all_models(self) -> list[DiscoveredModel]:
        """Discover all installed models from /api/tags, inspect /api/ps and /api/show."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                res = await client.get(f"{self.base_url}/api/tags")
                if res.status_code != 200:
                    raise OllamaDiscoveryError(
                        f"Ollama /api/tags returned status {res.status_code}",
                        code="ollama_api_error",
                    )
                tags_data = res.json()
        except httpx.ConnectError as e:
            logger.error("Cannot connect to Ollama service at %s: %s", self.base_url, e)
            raise OllamaDiscoveryError(
                f"Cannot connect to Ollama at {self.base_url}. Service may be offline.",
                code="ollama_offline",
            ) from e
        except Exception as e:
            logger.error("Error connecting to Ollama at %s: %s", self.base_url, e)
            raise OllamaDiscoveryError(
                f"Failed to discover models from Ollama: {e}",
                code="ollama_discovery_failed",
            ) from e

        running_models = await self.list_running_models()
        models_list = tags_data.get("models", [])
        discovered: list[DiscoveredModel] = []

        for m in models_list:
            name = m.get("name") or m.get("model")
            if not name:
                continue
            digest = m.get("digest") or ""
            size_bytes = m.get("size")
            details = m.get("details") or {}
            capabilities = m.get("capabilities") or []

            # Call /api/show for detailed configuration
            show_data = await self.get_model_details(name)

            # Extract context length from details or model_info
            context_length = details.get("context_length")
            if not context_length and show_data:
                model_info = show_data.get("model_info") or {}
                for k, v in model_info.items():
                    if "context_length" in k and isinstance(v, int):
                        context_length = v
                        break

            # Check if capabilities exist in show_data
            if not capabilities and show_data:
                capabilities = show_data.get("capabilities") or []

            is_loaded = name in running_models
            resource_obs = running_models.get(name, {})

            discovered.append(
                DiscoveredModel(
                    name=name,
                    digest=digest,
                    size_bytes=size_bytes,
                    parameter_size=details.get("parameter_size"),
                    quantization_level=details.get("quantization_level"),
                    context_length=context_length,
                    family=details.get("family"),
                    format=details.get("format"),
                    advertised_capabilities=capabilities,
                    is_loaded=is_loaded,
                    resource_observations=resource_obs,
                    raw_metadata=show_data,
                )
            )

        return discovered
