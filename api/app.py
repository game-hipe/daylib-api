import asyncio

from typing import TYPE_CHECKING, Any, Literal
from datetime import datetime, timedelta, timezone

import jwt

from fastapi import FastAPI, APIRouter, Request, Depends, Query, Body, status
from fastapi import HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, HttpUrl
from argon2 import PasswordHasher
from jwt.exceptions import InvalidTokenError
from argon2.exceptions import VerifyMismatchError

if TYPE_CHECKING:
    from core.manager.database import ModelManager, SearchManager
    from core.manager.spider import SpiderManager
    from core.manager.alert import AlertManager

from core.entitie.schema import GetContent, PaginationSchema
from core.config import setting
from core import __version__

from .utils import pagination
from .endpoint.manga import MangaAPI
from .endpoint.hentai import HentaiAPI
from .endpoint.spider import SpiderAPI


class CustomOuat2Password(OAuth2PasswordBearer):
    async def __call__(self, request: Request) -> str | Literal["Service-Pass"] | None:
        if token := request.headers.get("Service-Token-WWW"):
            if token == setting.service_key:
                return "Service-Pass"

            if self.auto_error:
                raise self.make_not_authenticated_error()

        return await super().__call__(request)


oauth2_scheme = CustomOuat2Password(tokenUrl="token")


class Token(BaseModel):
    access_token: str
    token_type: str


class ContentAPI:
    def __init__(
        self,
        model: ModelManager,
        search: SearchManager,
        spider: SpiderManager,
        alert: AlertManager,
    ):
        self.app = FastAPI(root_path="/api/v1")

        self.content_router = APIRouter(tags=["content"])

        self.model = model
        self.search = search
        self.spider = spider
        self.alert = alert
        self.hasher = PasswordHasher()

        self.config = setting

        self.__username = self.config.admin_login
        self.__hash = self.hasher.hash(self.config.admin_password)
        self._init_endpoint()

    def _init_endpoint(self):
        self.content_router.add_api_route(
            "/get/random", self.get_random_content, methods=["GET"]
        )
        self.content_router.add_api_route(
            "/get/url", self.get_content_by_url, methods=["GET"]
        )
        self.content_router.add_api_route(
            "/get/id", self.get_content_by_id, methods=["GET"]
        )

        self.content_router.add_api_route(
            "/search", self.search_content_all, methods=["POST"]
        )
        self.content_router.add_api_route(
            "/search/field", self.search_content_by_field, methods=["POST"]
        )
        self.content_router.add_api_route(
            "/search/fields", self.search_content_by_fields, methods=["POST"]
        )
        self.content_router.add_api_route(
            "/search/text", self.search_content_by_text, methods=["POST"]
        )

        self.app.include_router(self.content_router)

        self._manga = MangaAPI(self, prefix="/manga", tags=["manga"])
        self._hentai = HentaiAPI(self, prefix="/hentai", tags=["hentai"])
        self._spider = SpiderAPI(
            self,
            prefix="/spider",
            tags=["spider"],
            dependencies=[Depends(self.admin_depends)],
        )

        self.app.add_api_route("/token", self.login, methods=["POST"], tags=["system"])
        self.app.add_api_route("/health", self.health, methods=["GET"], tags=["system"])

    async def get_content_by_id(
        self, id: int = Query(description="Уникальный ID в БД")
    ) -> GetContent:
        """Получить обьект с помошью ID"""
        content = await self.model.get_content(mode="id", value=id)
        if content is None:
            raise HTTPException(
                status_code=404, detail=f"Контент с ID `{id}`, не найдено."
            )

        return content

    async def get_content_by_url(
        self, url: HttpUrl = Query(description="URL для обьекта который находится в БД")
    ) -> GetContent:
        """Получить обьект с помошью URL"""
        content = await self.model.get_content(mode="url", value=str(url))
        if content is None:
            raise HTTPException(
                status_code=404, detail=f"Контент с URL `{url}`, не найдено."
            )

        return content

    async def get_random_content(
        self,
        tag: str | None = Query(
            None, description="Тэг в котором исключительно будет поиск"
        ),
    ) -> GetContent:
        """Получить рандмоный контент из БД"""
        return await self.model.random_content(tag)

    async def search_content_by_field(
        self,
        field: str = Query(description="Название заполнение пример: `genre`"),
        value: str | list[str] = Body(
            description="Значение заполнение пример: `Драма`"
        ),
        pgnt: dict[str, Any] = Depends(pagination),
    ) -> PaginationSchema:
        """Искать с помошью заполнение"""
        return await self.search.search_by_field(field=field, value=value, **pgnt)

    async def search_content_by_fields(
        self,
        fields: dict[str, list[str]] = Body(description="Заполнение для поиска"),
        strict_mode: bool = Query(
            True,
            description="Строгий режим ищет только те произведение у которых есть все заполнение.",
        ),
        pgnt: dict[str, Any] = Depends(pagination),
    ) -> PaginationSchema:
        """Искать с помошью заполнений пример данных

        Examples:
            {
                "fields": {
                    "genre": [
                        "Ромком"
                    ],
                    "author": [
                        "GameHipe"
                    ]
                }
            }
        """
        return await self.search.search_by_fields(
            fields=fields, strict_mode=strict_mode, **pgnt
        )

    async def search_content_by_text(
        self,
        text: str = Query(
            description="Текст для поиска, который находится либо в описании либо в названии"
        ),
        pgnt: dict[str, Any] = Depends(pagination),
    ) -> PaginationSchema:
        """Искать по названию"""
        return await self.search.search_by_title(text=text, **pgnt)

    async def search_content_all(
        self, pgnt: dict[str, Any] = Depends(pagination)
    ) -> PaginationSchema:
        """Пагинация по всей БД, без особых значений"""
        return await self.search.search(**pgnt)

    async def admin_depends(self, token: str = Depends(oauth2_scheme)):
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Не удалось проверить учетные данные.",
            headers={"WWW-Authenticate": "Bearer"},
        )
        if token == "Service-Pass":
            return {"role": "service"}

        try:
            return jwt.decode(
                token, self.config.secret_key, algorithms=[self.config.algorithm]
            )

        except InvalidTokenError:
            raise credentials_exception

    async def login(
        self, form_data: OAuth2PasswordRequestForm = Depends()
    ) -> Token:  # NOTE: На будущее, что-бы можно было добавить больше админов
        if form_data.username != self.__username:
            raise HTTPException(status_code=400, detail="Неправильный логин или пароль")

        try:
            await asyncio.to_thread(self.hasher.verify, self.__hash, form_data.password)
            return Token(
                access_token=self.create_access_token(
                    {"username": form_data.username, "role": "admin"}
                ),
                token_type="bearer",
            )
        except VerifyMismatchError:
            raise HTTPException(
                status_code=400, detail="Incorrect username or password"
            )

    def create_access_token(self, data: dict, expires_delta: timedelta | None = None):
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=15)

        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(
            to_encode, self.config.secret_key, algorithm=self.config.algorithm
        )
        return encoded_jwt

    async def health(self):
        return {
            "status": "ok",
            "version": __version__,
            "service": "API",
            "timestamp": datetime.now().isoformat(),
        }
