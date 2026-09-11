from unittest.mock import AsyncMock

import pytest

from core._utils import linear_backoff, magic_backoff, random_backoff
from core.abstract.client import ClientResponse
from core.exception import StatusCodeException


class DummyClient:
    interval = 2


def make_response(error=None, attempt=3):
    return ClientResponse(
        url="https://example.com",
        attempt=attempt,
        client=DummyClient(),
        error=error,
    )


@pytest.mark.asyncio
async def test_random_backoff(monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr("core._utils.asyncio.sleep", sleep)
    monkeypatch.setattr("core._utils.random", lambda: 0.5)

    await random_backoff(make_response())

    sleep.assert_awaited_once_with(1.0)


@pytest.mark.asyncio
async def test_linear_backoff(monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr("core._utils.asyncio.sleep", sleep)

    await linear_backoff(make_response(attempt=4))

    sleep.assert_awaited_once_with(8)


@pytest.mark.asyncio
async def test_magic_backoff_without_error(monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr("core._utils.asyncio.sleep", sleep)

    await magic_backoff(make_response())

    sleep.assert_awaited_once_with(2)


@pytest.mark.asyncio
async def test_magic_backoff_403(monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr("core._utils.asyncio.sleep", sleep)

    error = StatusCodeException("https://example.com", 403, DummyClient())
    await magic_backoff(make_response(error=error, attempt=3))

    sleep.assert_awaited_once_with(2 ** (2 * 3))


@pytest.mark.asyncio
async def test_magic_backoff_500(monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr("core._utils.asyncio.sleep", sleep)

    error = StatusCodeException("https://example.com", 500, DummyClient())
    await magic_backoff(make_response(error=error, attempt=3))

    sleep.assert_awaited_once_with(2 * 3)