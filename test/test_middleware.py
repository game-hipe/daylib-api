import pytest

from core.abstract.spider.middleware import SpiderMiddleware


class DummySpider:
    @classmethod
    def name(cls):
        return "DummySpider"


class MyMiddleware(SpiderMiddleware):
    def __init__(self, spider):
        super().__init__(spider)
        self.processed = []
        self.errors = []

    async def _process_result(self, result):
        self.processed.append(result)
        return result

    async def _handle_error(self, exception):
        self.errors.append(exception)


@pytest.mark.asyncio
async def test_info_decorator_process_result():
    middleware = MyMiddleware(DummySpider())

    async def gen():
        yield "a"
        yield None
        yield "b"

    decorated = middleware.info_decorator(gen)
    results = [item async for item in decorated()]

    assert results == ["a", None, None, "b"]
    assert middleware.processed == ["a", None, "b"]


@pytest.mark.asyncio
async def test_info_decorator_handle_error():
    middleware = MyMiddleware(DummySpider())

    async def bad_gen():
        yield "a"
        raise ValueError("boom")

    decorated = middleware.info_decorator(bad_gen)
    results = [item async for item in decorated()]

    assert results == ["a"]
    assert len(middleware.errors) == 1
    assert isinstance(middleware.errors[0], ValueError)