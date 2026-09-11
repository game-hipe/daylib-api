from __future__ import annotations

from typing import TYPE_CHECKING, Self

from fastapi import APIRouter

if TYPE_CHECKING:
    from .app import ContentAPI


class BaseAPI(APIRouter):
    __endpoints: list[Self] = []

    TAG: str | None = None

    def __init_subclass__(cls):
        super().__init_subclass__()
        cls.__endpoints.append(cls)

    def __init__(self, content: ContentAPI, **kwargs):
        super().__init__(**kwargs)
        self.content = content
        self._connect_endpoint()

        self.content.app.include_router(self)

    def _connect_endpoint(self):
        raise NotImplementedError("Endpoint-ы не подключены")
