from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "ai_knowledge_lab",
    broker=settings.celery_broker_url,
    include=[
        "app.tasks.health",
        "app.tasks.ingestion",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
    timezone="UTC",
    enable_utc=True,
)