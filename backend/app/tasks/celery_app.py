from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "bike_crm",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.webhooks",
        "app.tasks.notifications",
        "app.tasks.contracts",
        "app.tasks.maintenance",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Moscow",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,
    task_soft_time_limit=240,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    beat_schedule={
        "refresh-avito-tokens": {
            "task": "app.tasks.webhooks.refresh_avito_tokens",
            "schedule": 21600.0,
        },
        "check-overdue-tasks": {
            "task": "app.tasks.notifications.check_overdue_tasks",
            "schedule": 900.0,
        },
        "poll-email-inbox": {
            "task": "app.tasks.webhooks.poll_email_inbox",
            # Чем чаще смотрим ящик, тем быстрее письмо доходит до чата
            "schedule": 20.0,
        },
        "daily-backup": {
            "task": "app.tasks.maintenance.daily_backup",
            "schedule": 86400.0,
        },
    },
)

celery_app.autodiscover_tasks()