from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from ..abstract.alert import LEVEL, BaseAlert


class AlertManager:
    """Менеджер увведомлений"""

    def __init__(self, *alert: BaseAlert):

        self.alerts = list(alert)
        self._lock = asyncio.Lock()

    async def send_message(  # NOTE: Возможно в будущем попробуем использовать брокеры по типу RabbitMQ
        self, message: str, level: LEVEL = "info"
    ) -> None:
        """Отправить сообшение всем alert-ам

        Args:
            message (str): Само сообщение
            level (LEVEL, optional): Уровение сообщение. По умолчанию "info".
        """
        for alert_item in self.alerts:
            asyncio.create_task(self._send_message(alert_item, message, level))

    async def _send_message(self, alert: BaseAlert, message: str, level: LEVEL):
        """Отправить сообщение для конкретного alert-а, но с обработкой.

        Args:
            alert (BaseAlert): Класс в который будет отправлен alert
            message (str): Само сообщение
            level (LEVEL, optional): Уровение сообщение. По умолчанию "info".
        """
        try:
            success = await alert.alert(message, level)
            if not success and alert.delete:
                await self.delete_alert(alert)

        except Exception:  # noqa: BLE001
            if alert.delete:
                self.delete_alert(alert)

            logger.exception(
                f"Не удалось отправить сообщение (alert_system={alert.name()!r}, message={message!r}, level={level!r})",
                extra={
                    "alert_system": alert.name(),
                    "message": message,
                    "level": level,
                },
            )

    async def delete_alert(self, alert: BaseAlert):
        """Удалить alert

        Args:
            alert (BaseAlert): alert
        """
        async with self._lock:
            logger.info(
                f"Удалена система оповещений (alert_system={alert.name()!r})",
                extra={"alert_system": alert.name()},
            )
            self.alerts.remove(alert)

    async def add_alert(self, alert: BaseAlert):
        """Добавить alert"""
        async with self._lock:
            logger.info(
                f"Добавлена новая система оповещений (alert_system={alert.name()!r})",
                extra={"alert_system": alert.name()},
            )
            self.alerts.append(alert)
