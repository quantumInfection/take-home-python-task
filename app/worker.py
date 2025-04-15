from celery import Celery
from app.core.config import settings

# Initialize Celery
celery_app = Celery(
    "bittensor_tasks",
    broker=settings.REDIS_BROKER_URL,
    backend=settings.REDIS_BACKEND_URL,
)

# Optional Celery configurations
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    # Set reasonable default time limits aligned with our specific task requirements
    # Sentiment analysis takes ~10s, blockchain operations ~15s
    # We set global limits slightly higher to account for overhead
    task_time_limit=20,  # 20 seconds default max task execution time
    task_soft_time_limit=16,  # 16 seconds default soft limit for graceful shutdown
    # Explicit retry configuration to standardize retry behavior across all tasks
    task_default_retry_delay=5,  # 5 seconds delay between retries
    task_max_retries=3,  # Maximum of 3 retries before giving up
    # These defaults are overridden by per-task settings where specified
    # Increase prefetch multiplier for better throughput
    worker_prefetch_multiplier=4,  # Prefetch multiple tasks to increase throughput
    # Keep task_acks_late for reliability, but with higher prefetch to balance
    task_acks_late=True,  # Acknowledge task after task is completed
    # Additional performance settings
    worker_max_tasks_per_child=1000,  # Restart worker after 1000 tasks to prevent memory leaks
)

# Import tasks to register them with Celery
# These imports must be after celery_app initialization to avoid circular imports
import app.tasks.sentiment_tasks  # noqa
import app.tasks.blockchain_tasks  # noqa
