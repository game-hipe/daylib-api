import re

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...abstract.spider._bs import _SpiderSoup

from ...manager.client import AiohttpClient
from ..share import BaseSpider


class ExampleBookSpider(BaseSpider[AiohttpClient, dict]):
    """
    Учебный паук для сайта books.toscrape.com.

    Демонстрирует три ключевых сценария микро-фреймворка:
      1) Пагинация по кастомному URL-шаблону (PAGE_URL).
      2) Извлечение preview-карточек со страницы списка (get_page).
      3) Извлечение детальной информации со страницы товара (get_info).
    """

    # ------------------------------------------------------------------
    # Конфигурация паука (то, что обычно настраивает разработчик)
    # ------------------------------------------------------------------

    BASE_TAG = "books"
    BASE_URL = "https://books.toscrape.com"

    # Шаблон URL страницы пагинации. {page} подставляется в create_page_url().
    PAGE_URL = "/catalogue/page-{page}.html"

    # Регулярка для поиска общего числа страниц в блоке "Page 1 of 50".
    MAX_PAGE_PATTERN = r"Page\s+\d+\s+of\s+(\d+)"

    # Соответствие: CSS-класс звезды -> числовой рейтинг.
    # Например, класс "star-rating Three" -> 3.
    STARS_MAP: dict[str, int] = {
        "One": 1,
        "Two": 2,
        "Three": 3,
        "Four": 4,
        "Five": 5,
    }

    # ------------------------------------------------------------------
    # Публичный API паука: эти методы вызывает фреймворк
    # ------------------------------------------------------------------

    async def get_page(self, page: int, **kwargs) -> dict:
        """
        Получить одну страницу списка книг.

        Возвращает объект пагинации с preview-элементами и
        информацией о том, есть ли следующая / последняя страница.
        """
        url = self.create_page_url(page)

        async with self.client.request(url, **kwargs) as response:
            soup = self.create_soup(await response.read())

        items = self._parse_previews(soup, url)
        return self._build_pagination(page, items, soup)

    async def get_info(self, url: str, **kwargs) -> dict:
        """Получить детальную информацию об одной книге."""
        async with self.client.request(url, **kwargs) as response:
            soup = self.create_soup(await response.read())

        product = soup.select_required("article.product_page")

        return self.create_add(
            title=self._parse_title(product),
            url=url,
            poster=self._parse_poster(product),
            description=self._parse_description(product),
            other={
                "stars": self._parse_stars(product),
                "price": self._parse_price(product),
                # По логике нужно создать отдельную таблицу,
                # чтобы поиск шёл через неё, но для учебного примера — так.
            },
        )

    # ------------------------------------------------------------------
    # Парсинг страницы списка
    # ------------------------------------------------------------------

    def _parse_previews(self, soup: _SpiderSoup, url: str) -> list:
        """Собрать preview-карточки всех книг со страницы списка."""
        previews = []

        for article in soup.select("ol.row article.product_pod"):
            # Картинка-обложка.
            image_container = article.select_required("div.image_container")
            img = image_container.select_required("img")

            # Ссылка с названием книги.
            title_link = article.select_required("h3 a")

            previews.append(
                self.create_preview(
                    title=title_link["title"],
                    url=self.urljoin(title_link["href"], url),
                    poster=self.urljoin(img["src"]),
                )
            )

        return previews

    def _build_pagination(self, page: int, items: list, soup: _SpiderSoup) -> dict:
        """
        Собрать объект пагинации.

        Логика:
          * Если на странице есть блок "Page X of Y" — знаем общее
            количество страниц, отдаём его фреймворку.
          * Если блока нет — значит это конец списка. Определяем это
            по отсутствию кнопки "next".
        """
        total_pages = self._extract_total_pages(soup)

        if total_pages is not None:
            return self.create_pagination(
                current_page=page,
                items=items,
                total_page=total_pages,
            )

        has_next = soup.select_one("ul.pager li.next") is not None
        return self.create_pagination(
            current_page=page,
            items=items,
            end_page=not has_next,
        )

    def _extract_total_pages(self, soup: _SpiderSoup) -> int | None:
        """
        Вернуть общее число страниц или None, если его нет на странице.

        None означает: это либо последняя страница, либо сайт не
        публикует общее число страниц.
        """
        pager = soup.select_one("ul.pager li.current")
        if pager is None:
            return None

        match = re.search(self.MAX_PAGE_PATTERN, pager.get_text(strip=True))
        return int(match.group(1)) if match else None

    # ------------------------------------------------------------------
    # Парсинг страницы товара
    # ------------------------------------------------------------------

    def _parse_title(self, product: _SpiderSoup) -> str:
        """Название книги."""
        return product.select_required("h1").get_text(strip=True)

    def _parse_price(self, product: _SpiderSoup) -> str:
        """Цена без символа валюты ('£')."""
        return product.select_required("p.price_color").get_text(strip=True).lstrip("£")

    def _parse_poster(self, product: _SpiderSoup) -> str:
        """Абсолютный URL обложки."""
        return self.urljoin(product.select_required("img")["src"])

    def _parse_stars(self, product: _SpiderSoup) -> int:
        """
        Рейтинг в звёздах.

        Классы элемента выглядят так: ["star-rating", "Three"].
        Первый — служебный, второй — название рейтинга.
        """
        classes = product.select_required("p.star-rating")["class"]

        if len(classes) > 1:
            return self.STARS_MAP[classes[1]]

        return 0

    def _parse_description(self, product: _SpiderSoup) -> str:
        """
        Описание книги.

        У некоторых книг блока с описанием может не быть —
        в этом случае возвращаем пустую строку.
        """
        description_tag = product.select_one("div#product_description ~ p")
        return description_tag.get_text(strip=True) if description_tag else ""

    # ------------------------------------------------------------------
    # URL-хелперы
    # ------------------------------------------------------------------

    def create_page_url(self, page: int) -> str:
        """Сформировать абсолютный URL страницы пагинации."""
        return self.urljoin(self.PAGE_URL.format(page=page))
