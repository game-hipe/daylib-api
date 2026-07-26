import asyncio
from hashlib import sha256
from pathlib import Path
from typing import Any, Generic, overload

import aiofiles
import m3u8

from loguru import logger

from ...config import setting
from ...manager.client import AiohttpClient
from ...abstract.spider import BaseSpider
from ...abstract.spider import SpiderMiddleware
from ...abstract.spider.spider import _C
from ...exception import MaxAttemtException
from .model import HentaiVideoSchema, Hentai, HentaiVideo, HentaiReadyVideo
from ...tasks.video import (
    process_fragments,
    process_video,
    create_thumbanil,
    create_m3u8,
    DEFAULT_FRAGMENT_PATH,
    DEFAULT_M3U8_NAME,
    DEFAULT_VIDEO_NAME,
)


class BaseHentaiMiddleware(
    SpiderMiddleware["BaseHentaiSpider", list[HentaiVideoSchema]]
):
    def __init__(self, spider):
        super().__init__(spider)
        self.save_dir = Path(setting.video_path)
        self._custom_client: AiohttpClient | None = None

        self.save_dir.mkdir(parents=True, exist_ok=True)

    async def _process_result(self, result):
        if result.extra_kwargs:
            if (
                not await result.connection.obj_in_database(
                    Hentai, Hentai.content_id == result.content.id
                )
                or result.start_config.update
            ):
                hentai = Hentai(content_id=result.content.id)

                for video in result.extra_kwargs:
                    try:
                        if not video.use_custom:
                            hentai_video = await self._process_video(video)

                        else:
                            hentai_video = await self.spider.process_video(video)

                    except MaxAttemtException as e:
                        logger.error(
                            f"Не удалось получить видео (url={str(video.video_url or video.m3u8_url)!r}, message={e.message!r})",
                            extra={
                                "hentai_url": str(result.content.url),
                                "video": video.model_dump(mode="json"),
                                "client_message": e.message,
                            },
                        )
                        continue

                    except Exception:
                        logger.exception(
                            "Ошибка во время обработки видео",
                            extra={
                                "hentai_url": str(result.content.url),
                                "video": video.model_dump(mode="json"),
                            },
                        )
                        raise

                    hentai.videos.append(
                        HentaiVideo(
                            hentai_id=result.content.id,
                            video_path=hentai_video.video_path,
                            m3u8_path=hentai_video.m3u8_path,
                            thumbanil_path=hentai_video.thumbanil_path,
                            title=video.title,
                            episode=video.episode,
                            dub=video.dub,
                            other=video.other,
                        )
                    )

                result.connection.session.add(hentai)
                await result.connection.session.commit()

        return result

    async def _handle_error(self, exception):
        logger.exception(f"Ошибка во время попытки добавить хентай: {exception}")
        raise

    async def _process_video(self, video: HentaiVideoSchema) -> HentaiReadyVideo:
        """Обработать видео и подготовить его метаданные."""
        if video.video_url:
            return await self._process_video_url(video)

        return await self._process_m3u8_video(video)

    async def _process_video_url(self, video: HentaiVideoSchema) -> HentaiReadyVideo:
        video_path = await self._download_video(
            str(video.video_url), headers=video.headers
        )
        process_video.delay(str(video_path.absolute()))

        thumbanil_suffix = await self._prepare_thumbanil(
            video, output_dir=video_path.parent
        )
        return self._build_ready_video(
            video_path=video_path,
            m3u8_path=video_path.parent / DEFAULT_FRAGMENT_PATH / DEFAULT_M3U8_NAME,
            thumbanil_suffix=thumbanil_suffix,
            output_dir=video_path.parent,
            episode=video.episode,
            title=video.title,
            dub=video.dub,
        )

    async def _process_m3u8_video(self, video: HentaiVideoSchema) -> HentaiReadyVideo:
        chunks_dir = await self._download_m3u8(
            str(video.m3u8_url), headers=video.headers
        )
        process_fragments.delay(str(chunks_dir.absolute()))
        create_m3u8.delay(str(chunks_dir.absolute()))

        thumbanil_suffix = await self._prepare_thumbanil(
            video, output_dir=chunks_dir.parent
        )
        return self._build_ready_video(
            video_path=chunks_dir.parent / DEFAULT_VIDEO_NAME,
            m3u8_path=chunks_dir / DEFAULT_M3U8_NAME,
            thumbanil_suffix=thumbanil_suffix,
            output_dir=chunks_dir.parent,
            episode=video.episode,
            title=video.title,
            dub=video.dub,
        )

    async def _prepare_thumbanil(
        self, video: HentaiVideoSchema, output_dir: Path
    ) -> str:
        if video.thumbanil_url is None:
            create_thumbanil.delay(
                str((output_dir / DEFAULT_VIDEO_NAME).absolute()),
                wait=True,
            )
            return "jpg"

        return await self._download_thumbanil(
            str(video.thumbanil_url),
            output_dir,
            headers=video.headers,
        )

    def _build_ready_video(
        self,
        *,
        video_path: Path,
        m3u8_path: Path,
        thumbanil_suffix: str,
        output_dir: Path,
        episode: int | None,
        title: str | None,
        dub: str | None,
    ) -> HentaiReadyVideo:
        return HentaiReadyVideo(
            video_path=str(video_path.absolute()),
            m3u8_path=str(m3u8_path.absolute()),
            thumbanil_path=str((output_dir / f"poster.{thumbanil_suffix}").absolute()),
            episode=episode,
            title=title,
            dub=dub,
        )

    async def _download_video(
        self, url: str, headers: dict[str, Any] | None = None
    ) -> Path:
        """Скачать видео

        Args:
            url (str): URL к видео не путать с m3u8.
            headers (dict[str, Any] | None, optional): Заголовки для запрсов. По умолчанию None.

        Returns:
            Path: Путь к видео
        """
        client = await self._get_client()
        headers = headers or {}

        async with client.request(method="GET", url=url, **headers) as response:
            response.raise_for_status()

            content_type = response.headers.get("Content-Type", "")
            if "/" in content_type:
                video_suffix = content_type.rsplit("/", 1)[-1]
            else:
                video_suffix = "mp4"

            if not video_suffix.isalnum() or len(video_suffix) > 10:
                video_suffix = "mp4"

            video_dir = self.save_dir / sha256(url.encode()).hexdigest()
            video_dir.mkdir(parents=True, exist_ok=True)

            file_path = video_dir / f"video.{video_suffix}"

            async with aiofiles.open(file_path, "wb") as f:
                async for chunk in response.content.iter_chunked(8192):
                    await f.write(chunk)

        return file_path

    async def _download_m3u8(
        self, url: str, headers: dict[str, Any] | None = None
    ) -> Path:
        """Скачать M3U8 целиком

        Args:
            url (str): URL к M3U8 не путать с видео целиком
            headers (dict[str, Any] | None, optional): Заголовки для запрсов. По умолчанию None.

        Returns:
            Path: Путь к видео
        """
        client = await self._get_client()
        headers = headers or {}

        async with client.request(method="GET", url=url, **headers) as resp:
            resp.raise_for_status()
            playlist_text = await resp.text()

        playlist = m3u8.loads(playlist_text, uri=url)

        if playlist.is_variant:
            best_stream = max(playlist.playlists, key=lambda p: p.stream_info.bandwidth)
            async with client.request(
                method="GET", url=best_stream.absolute_uri, **headers
            ) as resp:
                resp.raise_for_status()
                media_text = await resp.text()
            media_playlist = m3u8.loads(media_text, uri=best_stream.absolute_uri)
        else:
            media_playlist = playlist

        chunks_path = self.save_dir / sha256(url.encode()).hexdigest() / "fragments"
        chunks_path.mkdir(parents=True, exist_ok=True)

        async def download_segment(index: int, segment: m3u8.Segment):
            seg_url = segment.absolute_uri
            file_name = f"segment_{index:04d}.ts"
            file_path = chunks_path / file_name

            async with client.request(method="GET", url=seg_url, **headers) as seg_resp:
                seg_resp.raise_for_status()
                async with aiofiles.open(file_path, "wb") as f:
                    async for chunk in seg_resp.content.iter_chunked(8192):
                        await f.write(chunk)

        tasks = [
            download_segment(i, seg) for i, seg in enumerate(media_playlist.segments)
        ]
        await asyncio.gather(*tasks)

        return chunks_path

    async def _download_thumbanil(
        self, url: str, save_dir: Path, headers: dict[str, Any] | None = None
    ) -> str:
        """Скачать постер

        Args:
            url (str): URL к постеру
            save_dir (Path): Директория для сохранение постера
            headers (dict[str, Any] | None, optional): Заголовки для запрсов. По умолчанию None.

        Returns:
            str: Суффикс постера
        """
        client = await self._get_client()
        headers = headers or {}

        async with client.request(method="GET", url=url, **headers) as response:
            response.raise_for_status()

            content_type = response.headers.get("Content-Type", "")
            if "/" in content_type:
                video_suffix = content_type.rsplit("/", 1)[-1]
            else:
                video_suffix = "jpg"

            if not video_suffix.isalnum() or len(video_suffix) > 10:
                video_suffix = "jpg"

            async with aiofiles.open(save_dir / f"poster.{video_suffix}", "wb") as file:
                async for chunk in response.content.iter_chunked(8192):
                    await file.write(chunk)

            return video_suffix

    async def _get_client(
        self,
    ) -> AiohttpClient:  # NOTE: Что лучше использовать текущий client, но забивать семафор сегментами или создать новый?
        if self._custom_client:
            return self._custom_client
        else:
            self._custom_client = await AiohttpClient.load(
                {
                    "max_concurrent": 30  # NOTE: Скачиваем `.ts` файлы, поэтому главня задача не забить семафор
                }
            )
            return self._custom_client


class BaseHentaiSpider(
    BaseSpider[_C, list[HentaiVideoSchema]], Generic[_C], abstract=True
):
    BASE_MIDDLEWARE = BaseHentaiMiddleware

    @overload
    def create_video(
        *,
        video_url: str,
        chapter_number: int = 1,
        chapter_name: str | None = None,
        headers: dict[str, Any] | None = None,
    ) -> HentaiVideoSchema: ...

    @overload
    def create_video(
        *,
        m3u8_url: str,
        chapter_number: int = 1,
        chapter_name: str | None = None,
        headers: dict[str, Any] | None = None,
    ) -> HentaiVideoSchema: ...

    def create_video(
        *,
        video_url: str | None = None,
        m3u8_url: str | None = None,
        chapter_number: int = 1,
        chapter_name: str | None = None,
        headers: dict[str, Any] | None = None,
    ) -> HentaiVideoSchema:
        if video_url is not None:
            return HentaiVideoSchema(
                video_url=video_url,
                chapter_number=chapter_number,
                chapter_name=chapter_name,
                headers=headers,
            )
        elif m3u8_url is not None:
            return HentaiVideoSchema(
                m3u8_url=m3u8_url,
                chapter_number=chapter_number,
                chapter_name=chapter_name,
                headers=headers,
            )
        raise ValueError("Either video_url or m3u8_url must be provided")

    async def process_video(self, video: HentaiVideoSchema) -> HentaiReadyVideo:
        raise NotImplementedError("Кастомный способ загрузки видео не указан")
