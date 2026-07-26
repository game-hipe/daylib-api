from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Callable
from functools import wraps
from typing import TYPE_CHECKING, Generic, ParamSpec, TypeVar

from loguru import logger

if TYPE_CHECKING:
    from .schema import MiddlewareInfoResult
    from .spider import BaseSpider

_T = TypeVar("_T", bound="BaseSpider")
_R = TypeVar("_R")
P = ParamSpec("P")


class SpiderMiddleware(ABC, Generic[_T, _R]):
    def __init__(self, spider: _T):
        self._spider = spider

    def info_decorator(
        self, fn: Callable[P, AsyncGenerator[MiddlewareInfoResult[_R] | None]]
    ) -> Callable[P, AsyncGenerator[MiddlewareInfoResult[_R] | None]]:
        """Синхронный метод-декоратор, возвращающий асинхронную обертку."""

        @wraps(fn)
        async def _info_wrapper(
            *args: P.args, **kwargs: P.kwargs
        ) -> AsyncGenerator[MiddlewareInfoResult[_R] | None]:
            try:
                async for result in fn(*args, **kwargs):
                    if not result:
                        yield result

                    yield await self._process_result(result)

            except Exception as e:  # noqa: BLE001
                logger.exception(
                    f"Ошибка во время обработки результат (middleware={self.__class__.__name__!r}, spider={self.spider.name()!r})",
                    extra={
                        "middleware": self.__class__.__name__,
                        "spider": self.spider.name(),
                    },
                )
                await self._handle_error(e)

        return _info_wrapper

    @abstractmethod
    async def _process_result(
        self, result: MiddlewareInfoResult[_R]
    ) -> MiddlewareInfoResult[_R] | None:
        """Абстрактный метод для обработки успешного результата."""

    @abstractmethod
    async def _handle_error(self, exception: Exception) -> None:
        """Абстрактный метод для обработки ошибок."""

    @property
    def spider(self) -> _T:
        return self._spider
