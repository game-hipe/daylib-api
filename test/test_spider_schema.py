import asyncio

import pytest

from core.abstract.spider._status import SpiderParsingStatus, wait_task
from core.abstract.spider.schema import _BasePagination


class DummySpider:
    @classmethod
    def name(cls):
        return "DummySpider"


@pytest.mark.asyncio
async def test_spider_parsing_status():
    async def noop():
        return None

    task = asyncio.create_task(noop())
    status = SpiderParsingStatus(
        DummySpider(),
        task=task,
        current_page=1,
        total_page=2,
    )

    assert status.is_end is False

    status.update(_BasePagination(current_page=2, total_page=2))

    assert status.is_end is True
    assert status.to_dict()["spider"] == "DummySpider"
    assert "DummySpider" in repr(status)

    await task


@pytest.mark.asyncio
async def test_wait_task():
    async def noop():
        return None

    statuses = [
        SpiderParsingStatus(DummySpider(), task=asyncio.create_task(noop()), end_page=True),
        SpiderParsingStatus(DummySpider(), task=asyncio.create_task(noop()), end_page=True),
    ]

    await wait_task(statuses)