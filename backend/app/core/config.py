from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_name: str = "AI Knowledge Lab"
    app_env: str = "development"

    max_upload_size_bytes: int = 5 * 1024 * 1024
    upload_storage_dir: Path = PROJECT_ROOT / "storage" / "uploads"

    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    celery_broker_url: str = "redis://127.0.0.1:16379/0"

    database_url: str

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:1.7b"
    ollama_timeout_seconds: float = 60.0

    # Governed agent runtime budgets (T260025)
    agent_max_steps: int = 8
    agent_max_tool_calls: int = 5
    agent_max_denials: int = 3
    agent_max_active_runs_per_user: int = 3
    agent_run_timeout_seconds: float = 120.0
    agent_llm_timeout_seconds: float = 60.0
    agent_llm_max_retries: int = 2
    agent_approval_ttl_seconds: int = 900
    agent_max_result_bytes: int = 16_000

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()