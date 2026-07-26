import asyncio
from typing import TYPE_CHECKING, Generic, TypeVar

from .schema import MiddlewareInfoResult, _BasePagination

if TYPE_CHECKING:
    from .spider import BaseSpider

_T = TypeVar("_T", bound="BaseSpider")


async def wait_task(tasks: list["SpiderParsingStatus"]):
    await asyncio.gather(*[task.wait_for_end() for task in tasks])


class SpiderParsingStatus(Generic[_T]):
    def __init__(
        self,
        spider: _T,
        start_kwargs: dict | None = None,
        current_page: int = 0,
        total_page: int = 1,
        end_page: bool = False,
        task: asyncio.Task | None = None,
    ):
        self.spider = spider
        self.task = task
        self.start_kwargs = start_kwargs

        self.current_page: int = current_page
        self.total_page: int = total_page
        self._is_end: bool = end_page

    @classmethod
    def load_from_result(
        cls, spider: _T, task: asyncio.Task, result: MiddlewareInfoResult
    ):
        return cls(
            spider,
            task,
            current_page=result.pagination.current_page,
            total_page=result.pagination.total_page,
            end_page=result.pagination.end_page,
        )

    def update(self, result: MiddlewareInfoResult | _BasePagination):
        if isinstance(result, MiddlewareInfoResult):
            result = result.pagination

        self.current_page = max(self.current_page, result.current_page)

        if self.total_page != result.total_page:
            self.total_page = result.total_page

        self._is_end = result.is_end

    @property
    def is_end(self) -> bool:
        return self._is_end or (self.task.done() if self.task else False)

    @property
    def message(self):
        procent = self.current_page / self.total_page * 100
        return (
            f"{self.spider.name()}("
            f"current_page={self.current_page!r}, "
            f"total_page={self.total_page!r}, "
            f"is_end={self.is_end!r}, "
            f"procent={procent:.2f}"
            ")"
        )

    def to_dict(self):
        return {
            "spider": self.spider.name(),
            "current_page": self.current_page,
            "total_page": self.total_page,
            "is_end": self.is_end,
            "procent": self.current_page / self.total_page * 100,
        }

    def __repr__(self):
        return self.message

    def task_done(self):
        return self.task.done()

    async def wait_for_end(self):
        try:
            await self.task
        except asyncio.CancelledError:
            pass
