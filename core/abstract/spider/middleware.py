from abc import ABC, abstractmethod
from functools import wraps
from typing import Generic, ParamSpec, TypeVar, Callable, AsyncGenerator, TYPE_CHECKING

if TYPE_CHECKING:
    from .spider import BaseSpider
    from .schema import MiddlewareInfoResult

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

            except Exception as e:
                yield await self._handle_error(e)

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
