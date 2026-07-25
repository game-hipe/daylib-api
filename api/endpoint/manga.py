from fastapi import HTTPException
from sqlalchemy import select

from ..base import BaseAPI
from core.spider.manga.model import ChapterSchema, Chapter


class MangaAPI(BaseAPI):
    def _connect_endpoint(self):
        self.add_api_route("/chapter", self.get_manga_chapter)
        self.add_api_route("/chapter/count", self.get_manga_chapter_count)

    async def get_manga_chapter(
        self, content_id: int, chapter_number: int
    ) -> ChapterSchema:
        async with self.content.model.connect() as connect:
            stmt = select(Chapter).where(
                Chapter.manga_id == content_id, Chapter.chapter_number == chapter_number
            )
            chapter = await connect.session.scalar(stmt)
            if chapter is None:
                raise HTTPException(
                    status_code=404,
                    detail="Глава или контент не найден, пожалуйста удостоверьтесь в его существовании",
                )

            return chapter.model_dump()

    async def get_manga_chapter_count(self, content_id: int) -> list[int]:
        async with self.content.model.connect() as connect:
            if not await connect.obj_in_database(
                Chapter, Chapter.manga_id == content_id
            ):
                raise HTTPException(
                    status_code=404,
                    detail="Контент не найден, пожалуйста удостоверьтесь в его существовании",
                )

            stmt = select(Chapter.chapter_number).where(Chapter.manga_id == content_id)
            chapter = await connect.session.scalars(stmt)
            return list(chapter.fetchall())
