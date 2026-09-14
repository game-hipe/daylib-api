import re

from ...manager.client import AiohttpClient
from ..share import BaseSpider
from ..share import RequiredObjNotFoundException


class ExampleBookSpider(BaseSpider[AiohttpClient, dict]):
    BASE_TAG = "book"
    BASE_URL = "https://books.toscrape.com"
    PAGE_URL = "/catalogue/page-{page}.html"  # Кастомный атрибут для пагинации
    MAX_PAGE_PATTERN = r"Page\s+\d+\s+of\s+(\d+)"

    async def get_page(self, page, **kwargs):  # Получить страницу
        async with self.client.request(
            self.create_page_url(page), **kwargs
        ) as response:
            soup = self.create_soup(await response.read())
            items = []
            for article in soup.select("ol.row article.product_pod"):
                image_container = article.select_required("div.image_container")
                img = image_container.select_required("img")

                poster = self.urljoin(img["src"])
                title_box = article.select_required("h3 a")

                items.append(
                    self.create_preview(
                        title=title_box["title"], url=title_box["href"], poster=poster
                    )
                )

            try:
                match = re.search(
                    self.MAX_PAGE_PATTERN,
                    soup.select_required("ul.pager li.current").get_text(strip=True),
                )
                if match:
                    total_pages = int(match.group(1))
                    return self.create_pagination(
                        current_page=page, items=items, total_page=total_pages
                    )
                else:
                    raise RequiredObjNotFoundException()
            except RequiredObjNotFoundException:
                end_page = not bool(soup.select_one("ul.pager li.next"))
                return self.create_pagination(
                    current_page=page, items=items, end_page=end_page
                )

    async def get_info( 
        self, url, **kwargs
    ):  # Получить информацию об конкретном разделе
        return self.create_add(
            title="Example",
            url=url,
            poster="https://example.com/poster.jpg",
            extra_kwargs={"example_kwargs": "lol"},
        )

    def create_page_url(self, page: int):
        return self.urljoin(self.PAGE_URL.format(page=page))
