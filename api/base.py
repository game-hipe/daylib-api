from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter
from fastapi.datastructures import Default
from fastapi.routing import APIRoute
from fastapi.utils import generate_unique_id
from starlette.responses import JSONResponse

if TYPE_CHECKING:
    from .app import ContentAPI


class BaseAPI(APIRouter):
    def __init__(
        self,
        content: ContentAPI,
        *,
        prefix="",
        tags=None,
        dependencies=None,
        default_response_class=Default(JSONResponse),  # noqa: B008
        responses=None,
        callbacks=None,
        routes=None,
        redirect_slashes=True,
        default=None,
        dependency_overrides_provider=None,
        route_class=APIRoute,
        on_startup=None,
        on_shutdown=None,
        lifespan=None,
        deprecated=None,
        include_in_schema=True,
        generate_unique_id_function=Default(generate_unique_id),  # noqa: B008
        strict_content_type=Default(True),  # noqa: B008
    ):
        super().__init__(
            prefix=prefix,
            tags=tags,
            dependencies=dependencies,
            default_response_class=default_response_class,
            responses=responses,
            callbacks=callbacks,
            routes=routes,
            redirect_slashes=redirect_slashes,
            default=default,
            dependency_overrides_provider=dependency_overrides_provider,
            route_class=route_class,
            on_startup=on_startup,
            on_shutdown=on_shutdown,
            lifespan=lifespan,
            deprecated=deprecated,
            include_in_schema=include_in_schema,
            generate_unique_id_function=generate_unique_id_function,
            strict_content_type=strict_content_type,
        )
        self.content = content
        self._connect_endpoint()

        self.content.app.include_router(self)

    def _connect_endpoint(self):
        raise NotImplementedError("Endpoint-ы не подключены")
