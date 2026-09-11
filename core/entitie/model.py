from typing import TYPE_CHECKING, Any, overload

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

MAX_URL_LENTGH = 2083


__all__ = ["Base", "ConnnectionFC", "Content", "ContentTag", "Field", "FieldTag"]


class Base(DeclarativeBase):
    def __repr__(self) -> str:
        cols = [c.name for c in self.__table__.columns]
        values = {col: getattr(self, col) for col in cols}
        return f"{self.__class__.__name__}({', '.join(f'{k}={v!r}' for k, v in values.items())})"


class _BaseTag(Base):
    __abstract__ = True
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)

    if TYPE_CHECKING:

        def __init__(self, *, id: int = ..., name: str = ...) -> None: ...


class ContentTag(_BaseTag):
    __tablename__ = "content_tag"

    content: Mapped[list[Content]] = relationship("Content", back_populates="tag")


class FieldTag(_BaseTag):
    __tablename__ = "field_tag"
    field: Mapped[list[Field]] = relationship("Field", back_populates="tag")


class ConnnectionFC(Base):
    __tablename__ = "connection_field_content"
    content_id: Mapped[int] = mapped_column(
        ForeignKey("content.id", ondelete="CASCADE"), primary_key=True
    )
    field_id: Mapped[int] = mapped_column(
        ForeignKey("field.id"), primary_key=True, index=True
    )

    if TYPE_CHECKING:

        def __init__(self, *, content_id: int = ..., field_id: int = ...) -> None: ...


class Field(Base):
    __tablename__ = "field"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(1023), index=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("field_tag.id"))

    tag: Mapped[FieldTag] = relationship("FieldTag", back_populates="field")

    content: Mapped[list[Content]] = relationship(
        "Content", secondary=ConnnectionFC.__table__, back_populates="fields"
    )

    if TYPE_CHECKING:

        @overload
        def __init__(
            self, *, id: int = ..., name: str = ..., tag_id: int = ...
        ) -> None: ...
        @overload
        def __init__(
            self, *, id: int = ..., name: str = ..., tag: FieldTag = ...
        ) -> None: ...

    def __repr__(self):
        return f"Field(id={self.id!r}, name={self.name!r}, tag_id={self.tag_id!r})"


class Content(Base):
    __tablename__ = "content"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(1024))
    url: Mapped[str] = mapped_column(String(MAX_URL_LENTGH), unique=True, index=True)
    poster: Mapped[str] = mapped_column(String(MAX_URL_LENTGH))
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    other: Mapped[Any | None] = mapped_column(JSON(), nullable=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("content_tag.id"))

    tag: Mapped[ContentTag] = relationship("ContentTag", back_populates="content")

    fields: Mapped[list[Field]] = relationship(
        "Field",
        secondary=ConnnectionFC.__table__,
        back_populates="content",
        passive_deletes=True,
    )

    if TYPE_CHECKING:

        @overload
        def __init__(
            self,
            *,
            id: int = ...,
            title: str = ...,
            url: str = ...,
            poster: str = ...,
            description: str | None = None,
            other: Any | None = None,
            tag_id: int = ...,
            fields: list[Field] = ...,
        ) -> None: ...

        @overload
        def __init__(
            self,
            *,
            id: int = ...,
            title: str = ...,
            url: str = ...,
            poster: str = ...,
            description: str | None = None,
            other: Any | None = None,
            tag: ContentTag = ...,
            fields: list[Field] = ...,
        ) -> None: ...

    def __repr__(self) -> str:
        return (
            f"Content(id={self.id}, title={self.title!r}, "
            f"url={self.url!r}, tag_id={self.tag_id})"
        )
