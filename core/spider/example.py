from .share import BaseSpider
from ..manager.client import AiohttpClient


class ExampleSpider(BaseSpider[AiohttpClient, dict]):
    BASE_TAG = "images"
    BASE_URL = "https://example.com"

    async def get_page(self, page, **kwargs):
        return self.create_pagination(
            current_page=page,
            items=[
                self.create_preview(
                    title="Example",
                    url="https://example.com",
                    poster="https://example.com/poster.jpg",
                )
            ],
            end_page=True,
        )

    async def get_info(self, url, **kwargs):
        return self.create_add(
            title="Example",
            url=url,
            poster="https://example.com/poster.jpg",
            extra_kwargs={"example_kwargs": "lol"},
        )
