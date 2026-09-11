import asyncio

import pytest

from core.abstract.alert import BaseAlert
from core.manager.alert import AlertManager


class FakeAlert(BaseAlert):
    def __init__(self, result=True, delete=False):
        super().__init__(delete)
        self.result = result
        self.messages = []

    async def alert(self, message, level, **kwargs):
        self.messages.append((message, level))
        return self.result


@pytest.mark.asyncio
async def test_send_message():
    alert = FakeAlert()
    manager = AlertManager(alert)

    await manager.send_message("hello", "info")
    await asyncio.sleep(0)

    assert alert.messages == [("hello", "info")]


@pytest.mark.asyncio
async def test_delete_alert_on_failure():
    alert = FakeAlert(result=False, delete=True)
    manager = AlertManager(alert)

    await manager.send_message("fail", "error")
    await asyncio.sleep(0)

    assert alert not in manager.alerts


@pytest.mark.asyncio
async def test_add_alert():
    manager = AlertManager()
    alert = FakeAlert()

    await manager.add_alert(alert)

    assert alert in manager.alerts