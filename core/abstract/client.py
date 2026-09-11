import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from random import choice
from typing import Generic, TypedDict, TypeVar, Unpack

from loguru import logger

from .._utils import magic_backoff
from ..exception import ClientException, MaxAttemtException

_S = TypeVar("_S")
_R = TypeVar("_R")


@dataclass
class ClientResponse:
    url: str
    attempt: int
    client: BaseClient
    error: ClientException | None = None


class ClientConfig(TypedDict, total=False):
    max_try: int
    max_concurrent: int
    interval: float

    proxy: list[str]
    proxy_try: int
    ban_proxy: bool

    wait_func: Callable[[ClientResponse], Awaitable]


class BaseClient(ABC, Generic[_S, _R]): # noqa: UP046
    def __init__(self, session: _S, **config: Unpack[ClientConfig]):
        """Создание клиента для запросов

        Args:
            session (_S): Сессия для запросов
        """
        self._session = session
        self._config = config

        self.max_try: int = config.get("max_try", 3)
        self.max_concurrent: int = config.get("max_concurrent", 5)
        self.interval: float = config.get("interval", 3)

        self.proxy: dict[str, int] = {proxy: 0 for proxy in config.get("proxy", [])}
        self.proxy_try: int = config.get("proxy_try", 3)
        self.ban_proxy: bool = config.get("ban_proxy", True)

        self.wait_func: Callable[[ClientResponse], Awaitable] = config.get(
            "wait_func", magic_backoff
        )

        self.semaphore = asyncio.Semaphore(self.max_concurrent)

    @property
    def session(self) -> _S:
        """Переданная сессия"""
        return self._session

    @property
    def config(self) -> ClientConfig:
        """Конфиг который был передан при инициализации"""
        return self._config.copy()

    @property
    def name(self) -> str:
        """Название клиента"""
        return self.__class__.__name__

    @asynccontextmanager
    async def request(
        self,
        url: str,
        method: str | None = None,
        wait_func: Callable[[ClientResponse], Awaitable] | None = None,
        raise_for_status: bool = True,
        **kwargs,
    ) -> AsyncGenerator[_R]:
        """Запрос к ресурсу

        Args:
            url (str): URL - ресурса
            method (str | None, optional): Метод для запроса. По умолчанию None.
            wait_func(Callable[[ClientResponse], Awaitable] | None, optional): Кастомное время ожидание
            raise_for_status (bool, optional): Выбрасывать ли ошибку если статус не правильный

        Raises:
            MaxAttemtException: Если не удалось получить данные за отведённое количество попыток

        Returns:
            AsyncGenerator[_R]: Результат запроса
        """
        async with self.semaphore:
            response_yielded = False

            for try_count in range(1, self.max_try + 1):
                exception = None
                proxy = self.get_proxy()
                extra = {
                    "url": url,
                    "method": method,
                    "try_count": try_count,
                    "proxy": proxy,
                    "client": self.name,
                }
                logger.debug(
                    f"Запрос от клиента `{self.name}` (url={url!r}, method={method!r}, try_count={try_count!r}, proxy={proxy!r})",
                    extra=extra,
                )

                try:
                    async with self._request(
                        url, method, proxy, raise_for_status, **kwargs
                    ) as response:
                        response_yielded = True
                        yield response
                    return

                except ClientException as e:
                    exception = e
                    logger.error(e.error(), extra=extra)

                except Exception as e:
                    logger.error(
                        f"Неизвестная ошибка во время запроса: {e}", extra=extra
                    )
                    if response_yielded:
                        raise
                finally:
                    wait_func = wait_func or self.wait_func
                    await wait_func(
                        ClientResponse(
                            url=url, attempt=try_count, client=self, error=exception
                        )
                    )

            raise MaxAttemtException(url=url, max_try=self.max_try, client=self)

    @abstractmethod
    @asynccontextmanager
    async def _request(
        self,
        url: str,
        method: str | None = None,
        proxy: str | None = None,
        raise_for_status: bool = True,
        **kwargs,
    ) -> AsyncGenerator[_R]:
        """Настоящий запрос к ресурсу

        Args:
            url (str): URL - ресурса
            method (str | None, optional): Метод для запроса. По умолчанию None.
            proxy (str | None, optional): Прокси для запроса. По умолчанию None.
            raise_for_status (bool, optional): Выбрасывать ли ошибку если статус не правильный

        Returns:
            AsyncGenerator[_R]: Результат запроса
        """
        yield

    def get_proxy(self) -> str | None:
        """Получить рабочий прокси

        Returns:
            str | None: Прокси
        """
        work_proxy: list[str] = []
        for proxy, attempt in self.proxy.items():
            if self.ban_proxy:
                if attempt > self.max_try:
                    work_proxy.append(proxy)

            else:
                work_proxy.append(proxy)

        if work_proxy:
            return choice(work_proxy)

    def bad_proxy(self, proxy: str) -> None:
        """Метод что-бы указать что прокси плохо себя отработал

        Args:
            proxy (str): Прокси
        """
        if proxy not in self.proxy:
            logger.warning("Прокси не найден", extra={"proxy": proxy})
            return

        self.proxy[proxy] += 1

    def add_proxy(self, proxy: str) -> None:
        """Добавить прокси

        Args:
            proxy (str): прокси
        """
        if proxy in self.proxy:
            logger.warning("Прокси уже находится внутри памяти", extra={"proxy": proxy})
            return

        self.proxy[proxy] = 0

    @classmethod
    @abstractmethod
    async def load(cls, config: ClientConfig | None = None, **kwargs):
        """Создание собственного экземпляра со своей сессией
        kwargs - Передаётся в фабрику для создании сессии

        Args:
            config (ClientConfig | None, optional): Конфиг который будет передан в __init__
        """

    async def __aenter__(self):
        return self

    @abstractmethod
    async def __aexit__(self, exc_type, exc, tb): ...

    async def close(self):
        await self.__aexit__(None, None, None)
