from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Callable
from functools import wraps
from itertools import batched, count
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Generic,
    Literal,
    ParamSpec,
    Self,
    TypeVar,
    get_args,
    overload,
)
from urllib.parse import urljoin

from bs4 import _IncomingMarkup
from loguru import logger
from sqlalchemy.exc import IntegrityError

from ...entitie import AddContent, ChangeSchema, PreviewContent
from ...exception import SpiderException, _BaseException
from ..client import BaseClient
from ._bs import _SpiderSoup
from ._status import SpiderParsingStatus
from .schema import (
    GetInfoResult,
    MiddlewareInfoResult,
    Pagination,
    ParsingPaginationResult,
    _BasePagination,
)

if TYPE_CHECKING:
    from ...entitie.schema import GetContent  # type: ignore
    from ...manager.alert import LEVEL, AlertManager  # type: ignore
    from ...manager.database.model import ModelManager, _FastConnection  # type: ignore
    from .middleware import SpiderMiddleware  # type: ignore


_C = TypeVar("_C", bound="BaseClient")
_R = TypeVar("_R")
P = ParamSpec("P")


class _BuildSchema(ABC, Generic[_R]):
    BASE_URL: ClassVar[str]
    """Базовый URL сайта пример: `https://example.com`"""

    BASE_TAG: str | None = None
    """Базовый тег для обозночение в БД пример: `manga`"""

    def __init_subclass__(cls, abstract=False):
        super().__init_subclass__()
        if abstract:
            return

        if not hasattr(cls, "BASE_URL"):
            URL_ERROR_MESSAGE = f"Не найден URL у паука {cls}"
            logger.error(URL_ERROR_MESSAGE)
            raise ValueError(URL_ERROR_MESSAGE)

        if not cls.BASE_TAG:
            logger.info(
                f"Не был указан обычный тэг для паука {cls}, функция `create_content` теперь требует тэг"
            )

    def create_preview(
        self, title: str, url: str, poster: str, tag: str | None = None
    ) -> PreviewContent:
        """Создать схему для пагинации

        Args:
            title (str): Название
            url (str): URL
            poster (str): URL к постеру
            tag (str | None, optional): Тэг контента пример: `manga`, `anime`. По умолчанию None.

        Raises:
            ValueError: Если tag не передан и BASE_TAG не задан

        Returns:
            PreviewContent: Схема
        """
        if self.BASE_TAG is None and tag is None:
            raise ValueError("Параметр 'tag' обязателен, если BASE_TAG не задан!")

        return PreviewContent(
            title=title,
            url=self.urljoin(url),
            poster=self.urljoin(poster),
            tag=self.BASE_TAG or tag,
        )

    def create_add(
        self,
        title: str,
        url: str,
        poster: str,
        tag: str | None = None,
        description: str | None = None,
        other: Any | None = None,
        fields: dict[str, list[str]] | None = None,
        extra_kwargs: _R | None = None,
    ) -> GetInfoResult[_R]:
        """Создать полноценную схему для добавление данных в БД.

        Args:
            title (str): Название
            url (str): URL
            poster (str): URL к постеру
            tag (str | None, optional): Тэг контента пример: `manga`, `anime`. По умолчанию None.
            description (str | None, optional): Описание контента. По умолчанию None.
            other (Any | None, optional): Остальные параметры. По умолчанию None.
            fields (dict[str, list[str]] | None, optional): Заполнение которые важны при поиске. По умолчанию None.
            extra_kwargs (Any | None, optional): Дополнительные данные которые могут понадобиться в будущем

        Raises:
            ValueError: Если tag не передан и BASE_TAG не задан

        Returns:
            GetInfoResult: Схема
        """
        if self.BASE_TAG is None and tag is None:
            raise ValueError("Параметр 'tag' обязателен, если BASE_TAG не задан!")

        return GetInfoResult(
            content=AddContent(
                title=title,
                url=self.urljoin(url),
                poster=self.urljoin(poster),
                tag=self.BASE_TAG or tag,
                description=description,
                other=other,
                fields=fields,
            ),
            extra_kwargs=extra_kwargs,
        )

    def create_pagination(
        self,
        current_page: int,
        items: list[PreviewContent],
        total_page: int | None = None,
        end_page: bool | None = None,
    ) -> Pagination:
        """Создать схему пагинации

        Args:
            current_page (int): Текущая страница
            items (list[&quot;PreviewContent&quot;]): Предметы для пагинации
            total_page (int | None, optional): Общее количество страниц, нужно для пагинации пачками. По умолчанию None.
            end_page (bool | None, optional): Указать конец ли это страницы вручную, имеет приоритет у функции :class:`Pagination`. По умолчанию None.

        Returns:
            Pagination: Обьект пагинации
        """
        return Pagination(
            current_page=current_page,
            items=items,
            total_page=total_page,
            end_page=end_page,
        )

    def urljoin(self, url: str) -> str:
        """Соеденить относительный URL с базовым"""
        return urljoin(self.BASE_URL, url)


class BaseSpider(_BuildSchema[_R], Generic[_C, _R], abstract=True):
    BASE_FEATURES: str = "html.parser"
    """Базовый движок для парсинга"""

    BASE_BATCH: int = 10
    """Базовая количество одновременных запросов"""

    FIELDS_MAP: dict[str, str] | None = None
    """Карта для заполнений пример: `{'Теги': 'genre'}`"""

    BASE_MIDDLEWARE: list[type[SpiderMiddleware]] | type[SpiderMiddleware] | None = None
    """Базовые Middleware"""

    def __init__(
        self,
        client: _C,
        features: str | None = None,
        alert: AlertManager | None = None,
        batch: int | None = None,
        *,
        middleware: list[type[SpiderMiddleware]] | type[SpiderMiddleware] | None = None,
        use_middleware: bool = True,
        **kwargs,
    ):
        """Инициализаиция паука

        Args:
            client (_C): Клиент для запросов, подробнее в :class:`BaseClient`
            features (str | None, optional): Движок для парсинга. По умолчанию None.
            alert (AlertManager | None, optional): Система уведомлений. По умолчанию None.
            batch (int | None, optional): Количество одновременных запросов. По умолчанию None.
            middleware (list[type[&quot;SpiderMiddleware&quot;]] | type[&quot;SpiderMiddleware&quot;] | None, optional): Промежуточные классы для валидации, логирование, подробнее :class:`SpiderMiddleware`. По умолчанию None.
            use_middleware (bool, optional): Использовать ли middleware. По умолчанию True.
        """
        self._client = client
        self._kwargs = kwargs
        self._middleware = (
            middleware.copy()
            if isinstance(middleware, list)
            else [middleware]
            if middleware is not None
            else []
        )
        self._middleware.extend(
            self.BASE_MIDDLEWARE
            if isinstance(self.BASE_MIDDLEWARE, list)
            else [self.BASE_MIDDLEWARE]
            if self.BASE_MIDDLEWARE is not None
            else []
        )

        self.alert = alert
        self.features = features or self.BASE_FEATURES
        self.batch = batch or self.BASE_BATCH
        self.use_middleware = use_middleware
        self.middleware = [
            middleware_type(self) for middleware_type in self._middleware
        ]

        for _middleware in self.middleware:
            self.__set_info_middleware(_middleware)

        self._parsing: bool = False
        """Парсит ли на данный момент паук"""

    async def start_parsing(
        self,
        manager: ModelManager,
        start_page: int = 1,
        pagination_kwargs: dict | None = None,
        update: bool = False,
        **kwargs,
    ) -> SpiderParsingStatus[Self]:
        """Начать парсинг

        Args:
            manager (ModelManager): Менеджер для добавление данных в БД
            start_page (int, optional): Стартовая страница для парсинга. По умолчанию 1.
            pagination_kwargs (dict | None, optional): Ключевые параметры для пагинации, для функции :func:`pagination`. По умолчанию None.
            update (bool, optional): Обновлять ли контент если он находится в БД. По умолчанию False.

        Returns:
            SpiderParsingStatus: Обьект для отслеживание статуса
        """
        obj = SpiderParsingStatus(
            self,
            start_kwargs={
                "start_page": start_page,
                "pagination_kwargs": pagination_kwargs,
                "update": update,
            },
        )

        async def _start_check():
            async for _ in self.start_parsing_generator(
                manager=manager,
                start_page=start_page,
                pagination_kwargs=pagination_kwargs,
                update=update,
                status=obj,
                **kwargs,
            ):
                ...

        obj.task = asyncio.create_task(_start_check())
        return obj

    @abstractmethod
    async def get_page(self, page: int, **kwargs) -> Pagination:
        """Получить страницу

        Args:
            page (int): Номер страницы

        Returns:
            Pagination: Схема пагинации
        """

    @abstractmethod
    async def get_info(
        self, url: str, **kwargs
    ) -> GetInfoResult[_R] | AddContent | None:
        """Получить информацию по URL

        Args:
            url (str): URL к контенту

        Returns:
            AddContent | None: Схема которую можно добавить в БД при успешном запросе, иначе None
        """

    async def pagination(
        self,
        start_page: int = 1,
        batch: int | None = None,
        status: SpiderParsingStatus | None = None,
        **kwargs,
    ) -> AsyncGenerator[Pagination]:
        """Начать пагинацию по страницам

        Args:
            start_page (int, optional): Стартовая страница для пагинации. По умолчанию 1.
            batch (int | None, optional): Пачка для парсинга. По умолчанию None.

        Returns:
            AsyncGenerator[Pagination]: Асинхолнный итератор страниц
        """
        first_page = await self.get_page(start_page, **kwargs)
        if status:
            status.update(first_page)
        if first_page.is_end:
            yield first_page
            return

        if first_page.total_page:
            for pages in batched(
                range(start_page, first_page.total_page + 1), batch or self.batch
            ):
                tasks = [asyncio.create_task(self.get_page(p, **kwargs)) for p in pages]
                async for page in asyncio.as_completed(tasks):
                    page = await page
                    if status:
                        status.update(page)
                    yield page

        else:
            for page_num in count(start_page):
                result = await self.get_page(page_num, **kwargs)
                if status:
                    status.update(result)
                yield result
                if result.is_end:
                    return

    @overload
    async def full_pagination(
        self,
        start_page: int = 1,
        pagination_kwargs: dict | None = None,
        *,
        connection: _FastConnection,
        allow_unique: Literal[True],
        status: SpiderParsingStatus | None = None,
        **kwargs,
    ) -> AsyncGenerator[ParsingPaginationResult[_R]]:
        yield

    @overload
    async def full_pagination(
        self,
        start_page: int = 1,
        pagination_kwargs: dict | None = None,
        *,
        connection: _FastConnection | None = None,
        allow_unique: Literal[False],
        status: SpiderParsingStatus | None = None,
        **kwargs,
    ) -> AsyncGenerator[ParsingPaginationResult[_R]]:
        yield

    async def full_pagination(
        self,
        start_page: int = 1,
        pagination_kwargs: dict | None = None,
        *,
        connection: _FastConnection | None = None,
        allow_unique: bool = True,
        status: SpiderParsingStatus | None = None,
        **kwargs,
    ) -> AsyncGenerator[ParsingPaginationResult[_R]]:
        """Полная пагинация, возвращает добавляемый контент
        Если allow_unique = True, требует подключение к БД `connection`, так-как после получение данных мы будем проверять наличие контента в БД.
        Таким образом мы избавимся от дубликатов.

        Args:
            start_page (int, optional): Стратовая страница для парсинга. По умолчанию 1.
            pagination_kwargs (dict | None, optional): Ключевые параметры для пагинации, для функции :func:`pagination`. По умолчанию None.
            connection (_FastConnection | None, optional): Соединение с БД для проверки на уникальность. По умолчанию None.
            allow_unique (bool, optional): Разрешить ли уникальность, для работы требуется соединение с БД. По умолчанию True.
            status (SpiderParsingStatus | None, optional): Обьект для передачи статуса об парсинге.

        Returns:
            AsyncGenerator[ParsingPaginationResult[_R]]: Асинхолнный итератор добавляемого контента
        """
        async for page in self.pagination(
            start_page, status=status, **(pagination_kwargs or {})
        ):
            tasks: list[asyncio.Task[GetInfoResult[_R] | AddContent | None]] = []
            for item in page.items:
                if (
                    connection
                    and not allow_unique
                    and await connection.in_database(item.url)
                ):
                    continue

                tasks.append(
                    asyncio.create_task(self.get_info(str(item.url), **kwargs))
                )

            async for task in asyncio.as_completed(tasks):
                content = None
                try:
                    content = await task

                except _BaseException as e:
                    logger.error(e.error())

                except Exception as e:  # noqa: BLE001
                    logger.exception(
                        f"Неизвестная ошибка во время получение данных: {e}"
                    )

                if content is not None:
                    if isinstance(content, AddContent):
                        yield ParsingPaginationResult(
                            result=GetInfoResult(content=content),
                            current_page=page.current_page,
                            total_page=page.total_page,
                            end_page=page.end_page,
                        )
                        continue

                    yield ParsingPaginationResult(
                        result=content,
                        current_page=page.current_page,
                        total_page=page.total_page,
                        end_page=page.end_page,
                    )

    async def start_parsing_generator(
        self,
        manager: ModelManager,
        start_page: int = 1,
        pagination_kwargs: dict | None = None,
        update: bool = False,
        status: SpiderParsingStatus | None = None,
        **kwargs,
    ) -> AsyncGenerator[MiddlewareInfoResult[_R]]:
        """Начать парсинг, возвращает добавляенные данные из БД.

        Args:
            manager (ModelManager): Менеджер для добавление данных в БД
            start_page (int, optional): Стартовая страница для парсинга. По умолчанию 1.
            pagination_kwargs (dict | None, optional): Ключевые параметры для пагинации, для функции :func:`pagination`. По умолчанию None.
            update (bool, optional): Обновлять ли контент если он находится в БД. По умолчанию False.
            status (SpiderParsingStatus | None, optional): Обьект для передачи статуса об парсинге

        Return:
            AsyncGenerator[MiddlewareInfoResult[GetContent]]: Асинхронный генератор добавленных | обновлённых данных
        """
        try:
            self._parsing = True
            await self._alert(f"Паук `{self.name()}`, начал свою работу.", "info")
            async with manager.connect() as connection:
                async for content in self.full_pagination(
                    start_page=start_page,
                    pagination_kwargs=pagination_kwargs,
                    connection=connection,
                    allow_unique=update,
                    status=status,
                    **kwargs,
                ):
                    try:
                        pagination = _BasePagination.model_validate(content)
                        extra_kwargs = content.result.extra_kwargs
                        content = content.result.content
                        in_database = await connection.in_database(content.url)

                        if update and in_database:
                            other_params = {}
                            description = content.description
                            other = content.other
                            fields = content.fields

                            if description:
                                other_params["description"] = description

                            if other:
                                other_params["other"] = other

                            if fields:
                                other_params["fields"] = fields

                            yield MiddlewareInfoResult(
                                content=await manager.change_content(
                                    mode="url",
                                    value=str(content.url),
                                    change=ChangeSchema(
                                        title=content.title,
                                        url=content.url,
                                        poster=content.poster,
                                        **other_params,
                                    ),
                                ),
                                extra_kwargs=extra_kwargs,
                                connection=connection,
                                pagination=pagination,
                                start_config={
                                    "start_page": start_page,
                                    "pagination_kwargs": pagination_kwargs,
                                    "update": update,
                                    "kwargs": kwargs,
                                },
                            )

                        else:
                            if not in_database:
                                yield MiddlewareInfoResult(
                                    content=await manager.add_content(content),
                                    extra_kwargs=extra_kwargs,
                                    connection=connection,
                                    pagination=pagination,
                                    start_config={
                                        "start_page": start_page,
                                        "pagination_kwargs": pagination_kwargs,
                                        "update": update,
                                        "kwargs": kwargs,
                                    },
                                )

                    except asyncio.CancelledError, KeyboardInterrupt:
                        await self._alert(
                            f"Паук `{self.name()}`, был остановлен пользователем.",
                            "info",
                        )
                        return

                    except IntegrityError:
                        logger.warning(
                            f"Контент уже был добавлен в БД(title={content.title!r}, url={str(content.url)!r})"
                        )

                    except SpiderException as e:
                        logger.error(e.error())
        finally:
            if status:
                status._is_end = True
            await self._alert(f"Паук `{self.name()}`, завершил свою работу.", "info")
            self._parsing = False

    async def _alert(self, message: str, level: LEVEL) -> None:
        logger.log(level.upper(), message)
        if self.alert:
            await self.alert.send_message(message, level)
            return

    def fields_validate(
        self, fields: dict[str, list[str]], custom_map: dict[str, str] | None = None
    ) -> dict[str, list[str]]:
        """Валидация заполнений

        Args:
            fields (dict[str, list[str]]): Заполнение
            custom_map (dict[str, str] | None, optional): Карта для заполенений, меняет названий ключей. По умолчанию None.

        Returns:
            dict[str, list[str]]: Результат
        """
        fields = fields.copy()
        current_map = custom_map or self.FIELDS_MAP

        if current_map:
            for key, value in current_map.items():
                if key not in fields:
                    continue

                fields[value] = fields[key].copy()
                del fields[key]

        else:
            logger.warning(
                "Не указана ни одна карата, будут проведены обычные процедуры"
            )

        return {
            key.strip(): [x.strip() for x in value] for key, value in fields.items()
        }

    def __set_info_middleware(
        self, middleware: SpiderMiddleware[Self, GetContent]
    ) -> None:
        """Установить middleware

        Args:
            middleware (SpiderMiddleware): Обьект middleware
        """
        original_info: Callable[P, AsyncGenerator[MiddlewareInfoResult[GetContent]]] = (
            self.start_parsing_generator
        )

        @wraps(original_info)
        async def wrapper(
            *args: P.args, **kwargs: P.kwargs
        ) -> AsyncGenerator[MiddlewareInfoResult[GetContent]]:
            if self.use_middleware:
                decorator = middleware.info_decorator(original_info)
                async for result in decorator(*args, **kwargs):
                    if result is None:
                        continue

                    yield result
                return

            async for result in original_info(*args, **kwargs):
                yield result

        self.start_parsing_generator = wrapper

    def change_middleware(self) -> bool:
        """Изменить параметр `use_middleware` на противопложный

        Returns:
            bool: Текущий middleware
        """
        self.use_middleware = not self.use_middleware

    @property
    def client(self) -> _C:
        """Клиент для запросов"""
        return self._client

    @property
    def kwargs(self) -> Any:
        """Кварги переданные в паука во время инициализации"""
        return self._kwargs.copy()

    @classmethod
    def name(cls) -> str:
        return cls.__name__

    def create_soup(
        self, markup: _IncomingMarkup, features: str | None = None
    ) -> _SpiderSoup:
        """Создать Soup для парсинга

        Args:
            markup (_IncomingMarkup): Данные для парсинга
            features (str | None, optional): Движок для парсинга. По умолчанию None.

        Returns:
            _SpiderSoup: Кастомный Soup для парсинга подробнее :class:`_SpiderSoup`
        """
        return _SpiderSoup(markup=markup, features=features or self.features)

    @classmethod
    def need_client(cls) -> type[_C]:
        value = get_args(cls.__orig_bases__[0])[0]
        if isinstance(value, TypeVar):
            raise TypeError("Не указан необходимый тип")
        return value
