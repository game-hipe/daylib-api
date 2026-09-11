from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from core.abstract.client import BaseClient
from core.exception import ClientException, MaxAttemtException


class DummyClient(BaseClient[object, str]):
    @asynccontextmanager
    async def _request(
        self,
        url,
        method=None,
        proxy=None,
        raise_for_status=True,
        **kwargs,
    ):
        yield f"ok:{url}"

    @classmethod
    async def load(cls, config=None, **kwargs):
        return cls(object(), **(config or {}))

    async def __aexit__(self, exc_type, exc, tb):
        pass


class FailingClient(DummyClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.calls = 0

    @asynccontextmanager
    async def _request(
        self,
        url,
        method=None,
        proxy=None,
        raise_for_status=True,
        **kwargs,
    ):
        self.calls += 1
        raise ClientException(self, "boom")
        yield


@pytest.mark.asyncio
async def test_request_success():
    client = DummyClient(object())
    wait = AsyncMock()

    async with client.request("https://example.com", wait_func=wait) as response:
        assert response == "ok:https://example.com"

    wait.assert_awaited_once()
    response = wait.await_args.args[0]
    assert response.url == "https://example.com"
    assert response.attempt == 1
    assert response.error is None


@pytest.mark.asyncio
async def test_request_raises_max_attempt():
    client = FailingClient(object(), max_try=2)
    wait = AsyncMock()

    with pytest.raises(MaxAttemtException):
        async with client.request("https://example.com", wait_func=wait):
            pass

    assert client.calls == 2
    assert wait.await_count == 2


def test_proxy_management():
    client = DummyClient(object(), proxy=["p1", "p2"], ban_proxy=True, max_try=3)

    assert client.get_proxy() is None

    for _ in range(4):
        client.bad_proxy("p1")

    assert client.get_proxy() == "p1"

    client.add_proxy("p3")
    assert "p3" in client.proxy