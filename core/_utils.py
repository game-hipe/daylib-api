from __future__ import annotations

import asyncio
from random import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .abstract.client import ClientResponse

from .exception import StatusCodeException


async def random_backoff(response: ClientResponse):
    """Рандомное ожидание умножает на раномное число интерва

    Args:
        response (ClientResponse): Ответ от запроса
    """
    await asyncio.sleep(response.client.interval * random())


async def linear_backoff(response: ClientResponse):
    """Линейное ожидание, работает по формуле:
    `ИНТЕРВАЛ` * `КОЛИЧЕСТВО ПОПЫТОК`

    Args:
        response (ClientResponse): Ответ от запроса
    """
    await asyncio.sleep(response.client.interval * response.attempt)


async def magic_backoff(response: ClientResponse):
    """умное ожидани, ждёт в зависимости от ответа

    Args:
        response (ClientResponse): Ответ от запроса
    """
    if not response.error:
        await asyncio.sleep(response.client.interval)
        return

    sleep_time = response.client.interval
    if isinstance(response.error, StatusCodeException):
        if response.error.status == 403:
            response.client.interval * (2**response.attempt)

        if response.error.status == 500:
            sleep_time = response.client.interval * response.attempt

    await asyncio.sleep(sleep_time)
