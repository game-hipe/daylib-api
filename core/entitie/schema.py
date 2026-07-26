from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field, HttpUrl

_T = TypeVar("_T")


__all__ = [
    "AddContent",
    "ChangeSchema",
    "DataField",
    "GetContent",
    "PaginationSchema",
    "PreviewContent",
]


class _BaseContent(BaseModel, Generic[_T]):
    title: str
    url: HttpUrl
    poster: HttpUrl
    tag: _T


class _FieldContent(_BaseContent[_T], Generic[_T]):
    description: str | None = Field(None)
    other: Any | None = Field(None)
    fields: dict[str, list[_T]] | None = Field(None)


class DataField(BaseModel):
    id: int
    name: str


class AddContent(_FieldContent[str]): ...


class PreviewContent(_BaseContent[str]): ...


class GetContent(_FieldContent[DataField]):
    id: int


class ChangeSchema(BaseModel):
    title: str | None = Field(None)
    url: HttpUrl | None = Field(None)
    poster: HttpUrl | None = Field(None)
    tag: str | None = Field(None)
    description: str | None = Field(None)
    other: Any | None = Field(None)
    fields: dict[str, list[str]] | None = Field(None)


class PaginationSchema(BaseModel):
    current_page: int
    total_page: int
    total_items: int
    items: list[GetContent]
