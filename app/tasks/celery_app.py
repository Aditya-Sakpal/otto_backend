"""
Celery application for Otto backend background tasks.

Usage:
  # Start worker (processes tasks)
  celery -A app.tasks.celery_app worker --loglevel=info --pool=solo -Q follow_up

  # Start beat (triggers scheduled tasks)
  celery -A app.tasks.celery_app beat --loglevel=info
"""
import os
import sys

from dotenv import load_dotenv

# Load .env from the project root (two levels up from app/tasks/)
_root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(_root_dir, ".env"), override=False)

# contextual_follow_up_agent is a standalone package under app/agents/.
# Add that directory to sys.path so it can be imported by task modules.
_agents_dir = os.path.join(_root_dir, "app", "agents")
if _agents_dir not in sys.path:
    sys.path.insert(0, _agents_dir)

from celery import Celery
from celery.schedules import crontab

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "otto_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.tasks.follow_up_tasks"],
)

celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Prevent tasks from being acknowledged before they finish
    task_acks_late=True,
    # One retry on unexpected worker death
    task_reject_on_worker_lost=True,
    # Suppress Celery 6.0 deprecation warning
    broker_connection_retry_on_startup=True,
    # Always route follow-up tasks to the follow_up queue
    task_routes={
        "app.tasks.follow_up_tasks.run_contextual_follow_up": {"queue": "follow_up"},
    },
)

celery_app.conf.beat_schedule = {
    # Run the contextual follow-up agent every 6 hours.
    # Adjust the crontab to match your preferred cadence.
    "contextual-follow-up-every-6h": {
        "task": "app.tasks.follow_up_tasks.run_contextual_follow_up",
        "schedule": crontab(minute=0, hour="*/6"),
        "options": {"queue": "follow_up"},
    },
}
