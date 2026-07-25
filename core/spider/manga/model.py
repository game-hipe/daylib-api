from typing import overload, TYPE_CHECKING

from pydantic import BaseModel, HttpUrl, Field
from sqlalchemy.orm import Mapped, mapped_column, relationship, backref
from sqlalchemy import JSON, ForeignKey, Integer, String

from ...entitie.model import Base, Content


class ChapterSchema(BaseModel):
    images: list[HttpUrl]
    chapter_number: int = Field(1, ge=1)
    chapter_name: str | None = Field(None)


class Chapter(Base):
    __tablename__ = "manga_chapter"
    manga_id: Mapped[int] = mapped_column(
        ForeignKey("manga.content_id", ondelete="CASCADE"), primary_key=True
    )

    chapter_number: Mapped[int] = mapped_column(Integer(), default=1)
    chapter_name: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    images: Mapped[list[str]] = mapped_column(JSON())

    manga: Mapped["Manga"] = relationship("Manga", back_populates="chapters")

    def model_dump(self):
        return ChapterSchema(
            chapter_name=self.chapter_name,
            images=self.images,
            chapter_number=self.chapter_number,
        )

    if TYPE_CHECKING:

        @overload
        def __init__(
            self,
            *,
            manga_id: int = ...,
            images: list[str] = ...,
            chapter_name: str | None = ...,
        ): ...
        @overload
        def __init__(
            self,
            *,
            manga: "Manga" = ...,
            images: list[str] = ...,
            chapter_name: str | None = ...,
        ): ...


class Manga(Base):
    __tablename__ = "manga"

    content_id: Mapped[int] = mapped_column(ForeignKey("content.id"), primary_key=True)
    content: Mapped[Content] = relationship(Content, backref=backref("manga"))
    chapters: Mapped[list[Chapter]] = relationship("Chapter", back_populates="manga")

    if TYPE_CHECKING:

        @overload
        def __init__(self, *, content_id: int = ..., chapters: list[Chapter] = ...): ...
        @overload
        def __init__(
            self, *, content: Content = ..., chapters: list[Chapter] = ...
        ): ...
