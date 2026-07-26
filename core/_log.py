import sys
from pathlib import Path

from loguru import logger


def init():
    """Инициализировать логи"""
    log_dir = Path(".logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.remove()
    logger.add(sys.stdout, level="INFO")
    logger.add(
        log_dir / ".app_log.json",
        level="INFO",
        enqueue=True,
        serialize=True,
        rotation="100 MB",
    )
