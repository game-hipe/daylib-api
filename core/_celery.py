from celery import Celery

from .config import setting


def load_celery(main=None, backend=None, broker=None, **kwargs):
    return Celery(
        main,
        backend=backend or setting.backend,
        broker=broker or setting.broker,
        **kwargs,
    )
