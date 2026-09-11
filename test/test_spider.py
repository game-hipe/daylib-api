import pytest

from core.abstract.spider import BaseSpider


class DummyClient:
    name = "DummyClient"


class STestSpider(BaseSpider[DummyClient, dict]):
    BASE_URL = "https://example.com"
    BASE_TAG = "test"
    FIELDS_MAP = {"Теги": "genre"}

    async def get_page(self, page, **kwargs):
        return self.create_pagination(
            current_page=page,
            items=[],
            total_page=1,
            end_page=True,
        )

    async def get_info(self, url, **kwargs):
        return self.create_add(title="Test", url=url, poster="/poster.jpg")


def test_factories():
    spider = STestSpider(DummyClient())

    preview = spider.create_preview(title="Test", url="/1", poster="/poster.jpg")
    assert str(preview.url) == "https://example.com/1"
    assert str(preview.poster) == "https://example.com/poster.jpg"

    add = spider.create_add(
        title="Test",
        url="/1",
        poster="/poster.jpg",
        description="Desc",
    )
    assert add.content.title == "Test"
    assert str(add.content.url) == "https://example.com/1"

    pagination = spider.create_pagination(
        current_page=1,
        items=[preview],
        total_page=2,
    )
    assert pagination.current_page == 1
    assert pagination.total_page == 2


def test_urljoin_and_fields_validate():
    spider = STestSpider(DummyClient())

    assert spider.urljoin("/a") == "https://example.com/a"
    assert spider.urljoin("https://other.com/a") == "https://other.com/a"
    assert spider.fields_validate({"Теги": [" A ", " B "]}) == {
        "genre": ["A", "B"]
    }


def test_name_need_client_and_middleware_switch():
    spider = STestSpider(DummyClient())

    assert spider.name() == "STestSpider"
    assert spider.need_client() is DummyClient
    assert spider.use_middleware is True
    assert spider.change_middleware() is False
    assert spider.change_middleware() is True


def test_create_soup():
    spider = STestSpider(DummyClient())
    soup = spider.create_soup("<html><h1>Hi</h1></html>")

    assert soup.select_required("h1").text == "Hi"

    with pytest.raises(Exception):
        soup.select_required("h2")