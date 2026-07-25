from typing import TypeVar, Generic

from pydantic import BaseModel, Field, computed_field

from ...manager.database.model import _FastConnection
from ...entitie.schema import PreviewContent
from ...entitie.schema import AddContent, GetContent, _FieldContent

_T = TypeVar("_T")
_C = TypeVar("_C", bound=_FieldContent)


class _StartParsingconfig(BaseModel):
    start_page: int
    pagination_kwargs: dict | None
    update: bool
    kwargs: dict = Field(default_factory=dict)


class _BasePagination(BaseModel):
    current_page: int
    total_page: int | None = Field(None)
    end_page: bool | None = Field(None)

    @computed_field
    @property
    def is_end(self) -> bool:
        if self.end_page:
            return self.end_page

        if self.total_page:
            return self.current_page >= self.total_page

        return False


class Pagination(_BasePagination):
    items: list["PreviewContent"]


class _BaseInfoResult(BaseModel, Generic[_C, _T]):
    content: _C
    extra_kwargs: _T | None = Field(None)


class GetInfoResult(_BaseInfoResult[AddContent, _T], Generic[_T]): ...


class ParsingPaginationResult(_BasePagination, Generic[_T]):
    result: GetInfoResult[_T]


class MiddlewareInfoResult(_BaseInfoResult[GetContent, _T], Generic[_T]):
    model_config = {"arbitrary_types_allowed": True}
    connection: _FastConnection
    pagination: _BasePagination
    start_config: _StartParsingconfig
