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
    # Read timeout (max silence between bytes): bounds prompt evaluation for streaming
    # and the whole generation for non-streaming requests.
    # Defaults measured on a CPU-only host (T260040): a ~1.5k-token RAG prompt needs up
    # to ~50s of prompt evaluation for qwen3:1.7b, plus ~10s when the model is cold.
    ollama_timeout_seconds: float = 120.0
    ollama_connect_timeout_seconds: float = 5.0
    ollama_total_timeout_seconds: float = 180.0
    ollama_num_ctx: int = 4096
    ollama_num_predict: int = 512
    ollama_temperature: float | None = 0.0
    ollama_keep_alive: str = "30m"

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

    # Resource Governance & Reliability Hardening (T260028)
    rate_limit_enabled: bool = True
    rate_limit_redis_url: str = "redis://127.0.0.1:16379/0"
    rate_limit_auth_per_minute: int = 60
    rate_limit_rag_per_user_per_minute: int = 60
    rate_limit_rag_per_workspace_per_minute: int = 120
    rate_limit_agent_runs_per_user_per_minute: int = 30
    rate_limit_agent_runs_per_workspace_per_minute: int = 60
    rate_limit_benchmarks_per_workspace_per_hour: int = 20
    rate_limit_model_refresh_per_user_per_minute: int = 30

    # Inference Concurrency Controls (T260028)
    ollama_max_concurrency: int = 2
    ollama_max_queue_size: int = 10
    ollama_queue_timeout_seconds: float = 15.0

    # Agent Recovery & Leases (T260028)
    agent_tool_timeout_seconds: float = 30.0
    agent_run_lease_ttl_seconds: int = 60
    agent_max_recovery_attempts: int = 3

    # Production Reranker Integration (T260038)
    reranker_enabled: bool = False
    reranker_backend: str = "onnx_int8"
    reranker_model_path: Path = PROJECT_ROOT / "storage" / "models" / "reranker" / "model_int8.onnx"
    reranker_model_name: str = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
    reranker_pool_size: int = 10
    reranker_max_concurrency: int = 1
    reranker_max_queue_size: int = 5
    reranker_queue_timeout_seconds: float = 2.0
    reranker_intra_op_threads: int = 4
    reranker_timeout_ms: float = 3000.0
    reranker_expected_sha256: str | None = None

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()