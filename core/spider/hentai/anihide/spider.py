import asyncio
import re
from collections import defaultdict
from functools import lru_cache

import chompjs
from loguru import logger

from ....abstract.spider.spider import _SpiderSoup
from ....exception import ParseError, RequiredObjNotFoundException, StatusCodeException
from ....manager.client import AiohttpClient
from ..base import BaseHentaiSpider, HentaiVideoSchema


class AniHideSpider(BaseHentaiSpider[AiohttpClient]):
    BASE_URL = "https://online1.anihidee.org/"
    BASE_TAG = "hentai"
    IFRAME_RE = r"const\s+CONFIG\s*=\s*\{[\s\S]*?\};"
    REQUES_HEADERS = {"referer": BASE_URL}  # noqa: RUF012

    async def get_page(self, page, **kwargs):
        async with self.client.request(
            f"https://online1.anihidee.org/page/{page}", **kwargs
        ) as response:
            soup = self.create_soup(await response.read())
            items = []
            for card in soup.select("div#dle-content article.card"):
                try:
                    title = card.select_required("h2.card__title")
                    url = title.select_required("a").get("href")
                    poster = card.select_required("img")
                    items.append(
                        self.create_preview(
                            title=title.get_text(strip=True),
                            url=url,
                            poster=poster.get("data-src"),
                        )
                    )
                except ParseError:
                    continue

            total_page = max(
                int(x.get_text(strip=True))
                for x in soup.select_required("div.pagination__pages").children
                if x.get_text(strip=True).isdigit()
            )

            return self.create_pagination(
                current_page=page, items=items, total_page=total_page
            )

    async def get_info(self, url, **kwargs):
        try:
            async with self.client.request(
                url, raise_for_status=False, **kwargs
            ) as response:
                soup = self.create_soup(await response.read())
                if response.status == 403:
                    if self._check_on_guest(soup):
                        logger.debug(f"Реусур {url}, заблокирован для гостей")
                        return

                    else:
                        logger.error(
                            "Ресурс заблокирован, и не доступен",
                            meta={"status_code": response.status, "url": url},
                        )
                        return

            return await self.extract(soup)

        except StatusCodeException as e:
            if e.status == 403:
                logger.debug(f"Реусур {url}, заблокирован для пользователей")
                return

    async def extract(self, soup: _SpiderSoup):
        title = self._extract_title(soup)
        url = self._extract_url(soup)
        poster = self._extract_poster(soup)

        director = self._extract_director(soup)
        premiere = self._extract_premiere(soup)
        studio = self._extract_studio(soup)
        status = self._extract_status(soup)

        genres = self._extract_genres(soup)

        description = self._extract_description(soup)
        fields = {
            "director": director,
            "studio": studio,
            "genre": genres,
            "censorship": self._extract_censorship(soup),
        }

        if status:
            fields["status"] = [status]

        return self.create_add(
            title=title,
            url=url,
            poster=poster,
            description=description,
            other={"premiere": premiere},
            fields=fields,
            extra_kwargs=await self.extrct_iframe(soup),
        )

    async def extrct_iframe(self, soup: _SpiderSoup) -> list[HentaiVideoSchema]:
        videos: list[HentaiVideoSchema] = []
        iframes = self._extract_iframes(soup)

        async def _request(iframe: str):
            async with self.client.request(
                url=iframe, method="GET", headers=self.REQUES_HEADERS
            ) as response:
                videos.extend(
                    self._extract_iframe(self.create_soup(await response.read()))
                )

        await asyncio.gather(*[_request(iframe) for iframe in iframes])

        return videos

    def _extract_iframe(self, soup: _SpiderSoup) -> list[HentaiVideoSchema]:
        result: list[HentaiVideoSchema] = []
        for script in soup.select("script"):
            text = script.get_text(strip=True)
            if "const CONFIG" not in text:
                continue

            if match := re.search(self.IFRAME_RE, text, re.DOTALL):
                config = chompjs.parse_js_object(match.group())

                for number, episode in enumerate(config.get("episodes", []), start=1):
                    try:
                        if not episode.get("url"):
                            continue

                        result.append(
                            HentaiVideoSchema(
                                episode=episode.get("number", number),
                                title=episode.get("title"),
                                dub=config.get("currentDub"),
                                m3u8_url=episode["url"],
                                thumbanil_url=episode.get("poster"),
                                headers={
                                    "headers": {
                                        "referer": "https://ifr.animecrows.com/",
                                        "origin": "https://ifr.animecrows.com",
                                    }
                                },
                                other={
                                    "thumbnail": episode.get(
                                        "thumbnail"
                                    )  # Я хз что это за файл, но на будущее...
                                },
                            )
                        )
                    except Exception:  # noqa: BLE001
                        logger.exception("Не валидный JSON", extra={"config": config})
        return result

    def _extract_iframes(self, soup: _SpiderSoup) -> list[str]:
        iframes = [
            iframe["src"]
            for iframe in soup.select(
                "div.pmovie__player.tabs-block div.tabs-block__content iframe"
            )
            if iframe.get("src")
        ]
        if not iframes:
            raise RequiredObjNotFoundException(
                "Не найдены `iframe` по пути: `div.pmovie__player.tabs-block iframe`"
            )

        return iframes

    def _extract_title(self, soup: _SpiderSoup):
        if title := soup.select_required("h1"):
            return title.get_text(strip=True)

    def _extract_url(self, soup: _SpiderSoup):
        if url := soup.select_required('link[rel="canonical"]'):
            return url.get("href")

    def _extract_poster(self, soup: _SpiderSoup):
        if (poster := soup.select_required("div.pmovie__poster img")) and (
            url := poster.get("data-src")
        ):
            return self.urljoin(url)

    def _extract_rating(self, soup: _SpiderSoup) -> float | None:
        if rating := soup.select_one("div.card__rating-ext-count.centered-content"):
            return float(rating.get_text(strip=True))

    def _extract_director(self, soup: _SpiderSoup):
        if directors := self._extract_headers(soup).get("Режиссер"):
            return self._correct_headers(directors)
        return []

    def _extract_premiere(self, soup: _SpiderSoup):
        return self._extract_headers(soup).get("Премьера", [None])[0]

    def _extract_studio(self, soup: _SpiderSoup):
        if studios := self._extract_headers(soup).get("Студия"):
            return self._correct_headers(studios)
        return []

    def _extract_status(self, soup: _SpiderSoup):
        return self._extract_headers(soup).get("Статус", [None])[0]

    def _extract_voiceover(self, soup: _SpiderSoup):
        return self._correct_headers(self._extract_headers(soup).get("Озвучка", []))

    def _extract_subtitles(self, soup: _SpiderSoup):
        return self._correct_headers(self._extract_headers(soup).get("Субтитры", []))

    def _extract_censorship(self, soup: _SpiderSoup):
        return self._correct_headers(self._extract_headers(soup).get("Цензура", []))

    def _extract_genres(self, soup: _SpiderSoup):
        if genres := self._extract_headers(soup).get("Жанр"):
            if " / " in genres[0]:
                return genres[0].split(" / ")
            else:
                return genres[0].split(", ")
        return []

    @lru_cache(1)
    @staticmethod
    def _extract_headers(soup: _SpiderSoup) -> dict[str, list[str]]:
        result = defaultdict(list)
        for li in soup.select('ul[class*="pmovie__header-list"] li'):
            try:
                title, value = li.get_text(strip=True).split(":", 1)
            except ValueError:
                continue

            result[title].append(value.strip())

        return result

    def _extract_description(self, soup: _SpiderSoup) -> str | None:
        if description := soup.select_one("div.page__text"):
            return description.get_text(strip=True)

    def _correct_headers(self, items: list[str]) -> list[str]:
        result = []
        for item in items:
            item = item.replace(", ", " & ")
            if " & " in item:
                result.extend(x.strip() for x in item.split(" & "))
            else:
                result.append(item.strip())

        return result

    def _check_on_guest(self, soup: _SpiderSoup) -> bool:
        if title := soup.select_one("div.message-info div.message-info__title"):
            return title.get_text(strip=True) == "Внимание! Обнаружена ошибка"
        return False
