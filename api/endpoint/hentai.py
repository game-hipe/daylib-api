import os
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select

from core.spider.hentai.model import HentaiReadyVideo, HentaiVideo

from ..base import BaseAPI


class HentaiAPI(BaseAPI):
    _BASE = Path(os.environ.get("VIDEO_PATH", "./video")).resolve()

    def _connect_endpoint(self):
        self.add_api_route(
            "/series/metadata", self.get_series_metadata, methods=["GET"]
        )
        self.add_api_route(
            "/episod/metadata", self.get_episode_metadata, methods=["GET"]
        )

    async def get_series_metadata(self, content_id: int) -> list[HentaiReadyVideo]:
        async with self.content.model.connect() as connect:
            stmt = select(HentaiVideo).where(HentaiVideo.hentai_id == content_id)
            result = await connect.session.scalars(stmt)

            metadata = result.fetchall()
            if not metadata:
                raise HTTPException(
                    status_code=404,
                    detail=f"Серия видео с content_id = {content_id} не найден.",
                )

            return [self.hentai_fix(x.model_dump()) for x in metadata]

    async def get_episode_metadata(
        self, content_id: int, episode: int, dub: str
    ) -> HentaiReadyVideo:
        async with self.content.model.connect() as connect:
            stmt = select(HentaiVideo).where(
                HentaiVideo.hentai_id == content_id,
                HentaiVideo.episode == episode,
                HentaiVideo.dub == dub,
            )
            metadata = await connect.session.scalar(stmt)
            if not metadata:
                raise HTTPException(
                    status_code=404,
                    detail=f"Серия видео с content_id = {content_id} AND episode = {episode} AND dub = {dub} не найден.",
                )

            return self.hentai_fix(metadata.model_dump())

    def hentai_fix(self, hentai: HentaiReadyVideo, url_prefix: str = "/video"):
        hentai.m3u8_path = self.safe_path_to_url(
            hentai.m3u8_path, url_prefix=url_prefix
        )
        hentai.video_path = self.safe_path_to_url(
            hentai.video_path, url_prefix=url_prefix
        )
        hentai.thumbanil_path = self.safe_path_to_url(
            hentai.thumbanil_path, url_prefix=url_prefix
        )

        return hentai

    def safe_path_to_url(
        self,
        file_path: Path | str,
        base: str | Path | None = None,
        url_prefix: str = "/video",
    ):
        file_path = Path(file_path)
        if base is None:
            base = self._BASE
        else:
            base = Path(base).resolve()

        if not file_path.is_absolute():
            file_path = Path.cwd() / file_path

        full = file_path.resolve()

        try:
            relative = full.relative_to(base)
        except ValueError:
            try:
                relative = Path(file_path).relative_to(base)
            except ValueError:
                raise ValueError(f"Файл {file_path} не находится в {base}")

        url_path = str(relative).replace("\\", "/")

        if url_prefix:
            url_prefix = url_prefix.rstrip("/")
            if not url_prefix.startswith("/"):
                url_prefix = "/" + url_prefix
            return f"{url_prefix}/{url_path}"
        else:
            return f"/{url_path}"
