import pytest

from core.abstract.spider import BaseSpider
from core.abstract.client import BaseClient
from core.manager.client import AiohttpClient, PatchrightClient

def test_init_spider():
    class ExampleSpider(BaseSpider):
        BASE_URL = "https://example.com"

        async def get_info(self, url, **kwargs):
            return await super().get_info(url, **kwargs)

        async def get_page(self, page, **kwargs):
            return await super().get_page(page, **kwargs)

def test_init_invalid_spider():
    with pytest.raises(ValueError, match="Не найден URL"):
        class ExampleSpider(BaseSpider):
            async def get_info(self, url, **kwargs):
                return await super().get_info(url, **kwargs)

            async def get_page(self, page, **kwargs):
                return await super().get_page(page, **kwargs)

def test_init_abstract_spider():
    class ExampleSpider(BaseSpider, abstract = True):
        ...

def test_get_class_spider():
    class ExampleSpider(BaseSpider[BaseClient, None], abstract = True):
        ...

    assert ExampleSpider.need_client() == BaseClient


def test_get_class_spider():
    class ExampleSpider(BaseSpider[PatchrightClient, None], abstract = True):
        ...

    assert ExampleSpider.need_client() == PatchrightClient


def test_abc():
    class SpiderBase(BaseSpider[AiohttpClient, dict], abstract = True):
        ...

    class Spider(SpiderBase):
        BASE_URL = "https://example.com"

        async def get_info(self, url, **kwargs):
            return await super().get_info(url, **kwargs)

        async def get_page(self, page, **kwargs):
            return await super().get_page(page, **kwargs)

    assert Spider.need_client() == AiohttpClient
    assert SpiderBase.need_client() == AiohttpClient

def test_more_abc():
    class SpiderBase(BaseSpider[AiohttpClient, dict], abstract = True):
        ...

    class Spider(SpiderBase):
        BASE_URL = "https://example.com"

        async def get_info(self, url, **kwargs):
            return await super().get_info(url, **kwargs)

        async def get_page(self, page, **kwargs):
            return await super().get_page(page, **kwargs)

    class Spider2(SpiderBase):
        REQUEST_CLIENT = PatchrightClient
        BASE_URL = "https://example.com"

        async def get_info(self, url, **kwargs):
            return await super().get_info(url, **kwargs)

        async def get_page(self, page, **kwargs):
            return await super().get_page(page, **kwargs)

    class Spider3(Spider2):
        ...

    assert Spider.need_client() == AiohttpClient
    assert SpiderBase.need_client() == AiohttpClient
    assert Spider2.need_client() == PatchrightClient
    assert Spider3.need_client() == PatchrightClient