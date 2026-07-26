from ....manager.client import AiohttpClient
from ..base import BaseMangaSpider


class MultiMangaSpider(BaseMangaSpider[AiohttpClient]):
    BASE_URL = "https://multi-manga.com"
    BASE_TAG = "manga"
    FIELDS_MAP = {"Теги": "genre", "Автор": "author", "Язык": "language"}  # noqa: RUF012

    async def get_page(self, page, **kwargs):
        async with self.client.request(
            f"https://multi-manga.com/page/{page}/", **kwargs
        ) as response:
            soup = self.create_soup(await response.read())
            items = []
            for gallery in soup.select("div#dle-content div.gallery"):
                a = gallery.select_required("a")
                img = gallery.select_required("img")

                result = self.create_preview(
                    title=a.get_text(strip=True),
                    url=a.get("href"),
                    poster=img.get("data-src"),
                )
                items.append(result)

            return self.create_pagination(
                current_page=page,
                items=items,
                total_page=max(
                    [
                        int(x.get_text(strip=True))
                        for x in soup.select("section.pagination a")
                        if x.get_text(strip=True).isdigit()
                    ]
                    or [0]
                ),
            )

    async def get_info(self, url, **kwargs):
        async with self.client.request(url, **kwargs) as response:
            soup = self.create_soup(await response.read())
            title = soup.select_required("div#info h1")
            poster = soup.select_required("div#cover img")
            url = soup.select_required('link[rel="canonical"]')

            images = [
                img.get("data-src")
                for img in soup.select("div#thumbnail-container img")
                if img.get("data-src")
            ]

            fields = {}
            for tag in soup.select("section#tags div.tag-container"):
                if not tag.a or not tag.next:
                    continue

                fields |= self.fields_validate(
                    {
                        tag.next.get_text(strip=True): [
                            a.get_text(strip=True) for a in tag.select("a")
                        ]
                    }
                )

            return self.create_add(
                title=title.get_text(strip=True),
                url=url.get("href", url),
                poster=poster.get("data-src"),
                fields=fields,
                extra_kwargs=[self.create_chapter(images)],
            )
