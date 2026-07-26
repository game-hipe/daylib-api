from celery import Celery

from .config import setting

app = Celery(
    "daylib",
    backend=setting.backend,
    broker=setting.broker,
    include=["core.tasks.video", "core.manager.spider._worker"],
)

app.conf.update(
    task_routes={
        "core.tasks.*": {"queue": "media"},
    },
    task_default_queue="default",
)
