from typing import Any, TYPE_CHECKING, overload

from pydantic import BaseModel, HttpUrl, Field, model_validator
from sqlalchemy.orm import Mapped, mapped_column, relationship, backref
from sqlalchemy import JSON, ForeignKey, Integer, String

from ...entitie.model import Base, Content


class HentaiVideoSchema(BaseModel):
    episode: int = Field(1, ge=1)
    title: str | None = Field(None)
    dub: str | None = Field(None)

    video_url: HttpUrl | None = Field(None)
    m3u8_url: HttpUrl | None = Field(None)
    thumbanil_url: HttpUrl | None = Field(None)
    other: dict | None = Field(None)
    headers: dict[str, Any] | None = Field(None)

    use_custom: bool = Field(False)

    @model_validator(mode="after")
    def check_url(self):
        if not self.video_url and not self.m3u8_url:
            raise ValueError("Не указан ни URL для видео, и для m3u8 файла")
        return self


class HentaiReadyVideo(BaseModel):
    video_path: str
    m3u8_path: str
    thumbanil_path: str
    episode: int = Field(1, ge=1)
    title: str | None = Field(None)
    dub: str | None = Field(None)


class HentaiVideo(Base):
    __tablename__ = "hentai_video"

    id: Mapped[int] = mapped_column(primary_key=True)
    hentai_id: Mapped[int] = mapped_column(
        ForeignKey("hentai.content_id", ondelete="CASCADE")
    )

    episode: Mapped[int] = mapped_column(Integer(), default=1)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dub: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    video_path: Mapped[str] = mapped_column(String(512))
    m3u8_path: Mapped[str] = mapped_column(String(512))
    thumbanil_path: Mapped[str] = mapped_column(String(512))
    other: Mapped[dict] = mapped_column(JSON(), nullable=True)

    hentai: Mapped["Hentai"] = relationship("Hentai", back_populates="videos")

    def model_dump(self) -> HentaiReadyVideo:
        return HentaiReadyVideo(
            video_path=self.video_path,
            m3u8_path=self.m3u8_path,
            thumbanil_path=self.thumbanil_path,
            episode=self.episode,
            title=self.title,
            dub=self.dub,
        )

    if TYPE_CHECKING:

        @overload
        def __init__(
            self,
            *,
            hentai_id: int = ...,
            video_path: str = ...,
            m3u8_path: str = ...,
            thumbanil_path: str = ...,
            title: str | None = ...,
            episode: int | None = ...,
            dub: str | None = ...,
            other: dict | None = ...,
        ): ...
        @overload
        def __init__(
            self,
            *,
            hentai: "Hentai" = ...,
            video_path: str = ...,
            m3u8_path: str = ...,
            thumbanil_path: str = ...,
            title: str | None = ...,
            episode: int | None = ...,
            dub: str | None = ...,
            other: dict | None = ...,
        ): ...


class Hentai(Base):
    __tablename__ = "hentai"

    content_id: Mapped[int] = mapped_column(ForeignKey("content.id"), primary_key=True)
    content: Mapped[Content] = relationship(Content, backref=backref("hentai"))
    videos: Mapped[list[HentaiVideo]] = relationship(
        HentaiVideo, back_populates="hentai"
    )

    if TYPE_CHECKING:

        @overload
        def __init__(
            self, *, content_id: int = ..., videos: list[HentaiVideo] = ...
        ): ...
        @overload
        def __init__(
            self, *, content: Content = ..., videos: list[HentaiVideo] = ...
        ): ...
