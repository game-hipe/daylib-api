from ..share import BaseSpider
from ...manager.client import AiohttpClient


class ExampleSpider(BaseSpider[AiohttpClient, dict]):
    BASE_TAG = "images" # Базовый тэг, данные полученные отсюда сразу будут отмечены как images
    BASE_URL = "https://example.com" # Базовый URL, необходим для пагинации, urljoin и т п.

    async def get_page(self, page, **kwargs): # Получить страницу
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

    async def get_info(self, url, **kwargs): # Получить информацию об конкретном разделе
        return self.create_add(
            title="Example",
            url=url,
            poster="https://example.com/poster.jpg",
            extra_kwargs={"example_kwargs": "lol"},
        )
