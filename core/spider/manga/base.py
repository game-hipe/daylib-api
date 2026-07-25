from typing import Generic

from loguru import logger

from ...abstract.spider import BaseSpider
from ...abstract.spider import SpiderMiddleware
from ...abstract.spider.spider import _C
from .model import ChapterSchema, Manga, Chapter


class MangaMiddleware(SpiderMiddleware["BaseMangaSpider", list[ChapterSchema]]):
    async def _process_result(self, result):
        if result.extra_kwargs:
            if not await result.connection.obj_in_database(
                Manga, Manga.content_id == result.content.id
            ):
                manga = Manga(
                    content_id=result.content.id,
                    chapters=[
                        Chapter(
                            images=[str(x) for x in chapter.images],
                            chapter_name=chapter.chapter_name,
                        )
                        for chapter in result.extra_kwargs
                    ],
                )
                result.connection.session.add(manga)
                await result.connection.session.commit()

        return result

    async def _handle_error(self, exception):
        logger.exception(f"Ошибка во время попытки добавить мангу: {exception}")
        raise


class BaseMangaSpider(BaseSpider[_C, list[ChapterSchema]], Generic[_C], abstract=True):
    BASE_MIDDLEWARE = MangaMiddleware

    def create_chapter(
        self,
        images: list[str],
        chapter_number: int = 1,
        chapter_name: str | None = None,
    ) -> ChapterSchema:
        return ChapterSchema(
            images=[self.urljoin(x) for x in images],
            chapter_number=chapter_number,
            chapter_name=chapter_name,
        )
