from typing import Literal, TypeVar, AsyncGenerator, overload
from contextlib import asynccontextmanager

from loguru import logger
from pydantic import HttpUrl
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy import ColumnExpressionArgument, exists, func, select
from sqlalchemy.sql._typing import _ColumnExpressionArgument

from ._db import _BaseManager
from ...entitie import (
    AddContent,
    GetContent,
    Content,
    ContentTag,
    FieldTag,
    Field,
    DataField,
    ChangeSchema,
    Base,
)
from ...entitie.model import _BaseTag

_T = TypeVar("_T", bound=_BaseTag)
ModelType = TypeVar("ModelType", bound=Base)


class _FastConnection:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def in_database(self, url: str) -> bool:
        return await self._exists(Content, Content.url == str(url))

    async def obj_in_database(
        self,
        model: type[ModelType],
        *conditions: _ColumnExpressionArgument[bool],
    ) -> bool:
        return await self._exists(model, *conditions)

    async def _exists(
        self,
        model: type[ModelType],
        *conditions: ColumnExpressionArgument[bool],
    ) -> bool:
        """Внутренний метод для EXISTS запроса."""
        stmt = select(exists().where(*conditions).select_from(model))
        result = await self.session.scalar(stmt)
        return bool(result)  # Гарантированно возвращаем bool


class ModelManager(_BaseManager):
    @overload
    async def get_content(
        self, mode: Literal["id"], value: int
    ) -> GetContent | None: ...
    @overload
    async def get_content(
        self, mode: Literal["url"], value: str
    ) -> GetContent | None: ...
    @overload
    async def change_content(
        self, mode: Literal["id"], value: int, change: ChangeSchema
    ) -> GetContent: ...
    @overload
    async def change_content(
        self, mode: Literal["url"], value: str, change: ChangeSchema
    ) -> GetContent: ...
    @overload
    async def delete_content(self, mode: Literal["id"], value: int) -> bool: ...
    @overload
    async def delete_content(self, mode: Literal["url"], value: str) -> bool: ...

    async def add_content(self, content: AddContent) -> GetContent:
        """Добавить контент в базу данных, требует что-бы URL были разными иначе будет ошибка

        Args:
            content (AddContent): Добавляемый контент

        Returns:
            GetContent: Обьект данных из БД
        """
        logger.debug(
            f"Попытка добавить обьект в БД (title={content.title}, url={str(content.url)})",
            extra={"content": content.model_dump(mode="json")},
        )
        try:
            async with self.begin() as session:
                logger.debug("Получение тега контента")
                content_tag = await self._get_tag(session, ContentTag, content.tag)
                logger.debug(f"Тег контента получен id={content_tag.id!r}")

                content_fields: list[Field] = []
                if content.fields:
                    logger.debug(
                        f"Попытка получить все теги для контента (content_fields={list(content.fields.keys())})",
                        extra={"content_fields": content.fields},
                    )
                    content_fields = [
                        await self._get_tag(
                            session,
                            Field,
                            field_key,
                            tag=await self._get_tag(session, FieldTag, key),
                        )
                        for key, fields in content.fields.items()
                        for field_key in fields
                    ]
                    logger.debug(
                        f"Получены все теги для контента (content_fields={list(content.fields.keys())}, db_fields={content_fields})",
                        extra={
                            "content_fields": content.fields,
                            "db_fields": [
                                {"name": field.name, "id": field.id}
                                for field in content_fields
                            ],
                        },
                    )

                added_content = Content(
                    title=content.title,
                    url=str(content.url),
                    poster=str(content.poster),
                    description=content.description,
                    other=content.other,
                    tag=content_tag,
                    fields=content_fields,
                )
                session.add(added_content)
                await session.flush()

                get_content = GetContent(
                    title=content.title,
                    url=content.url,
                    poster=content.poster,
                    tag=DataField(id=content_tag.id, name=content_tag.name),
                    description=content.description,
                    other=content.other,
                    fields=self._get_fields(content_fields),
                    id=added_content.id,
                )
                logger.info(
                    f"Добавлен новый элемент в БД (id={get_content.id!r}, title={get_content.title!r}, url={str(get_content.url)!r})",
                    extra={
                        "content": content.model_dump(mode="json"),
                        "db_content": get_content.model_dump(mode="json"),
                    },
                )
                return get_content

        except Exception as e:
            logger.exception(
                f"Ошибка во время добавление данных в БД ( (title={content.title}, url={str(content.url)}, exception={e!r})",
                extra={"content": content.model_dump(mode="json"), "exception": str(e)},
            )
            raise

    async def get_content(
        self, mode: Literal["id", "url"], value: int | str
    ) -> GetContent | None:
        """Получить обьект из базы данных, поддерживает 2 режима, получение с помошью ID, и URL.

        Args:
            mode (Literal[&quot;id&quot;, &quot;url&quot;]): Режим поиска
            value (int | str): Значение для поиска

        Returns:
            GetContent | None: Обьект данных из БД если найдено иначе None
        """
        try:
            async with self.session() as session:
                if content := await self._get_content(session, mode, value):
                    get_content = GetContent(
                        id=content.id,
                        title=content.title,
                        url=content.url,
                        poster=content.poster,
                        tag=DataField(id=content.tag.id, name=content.tag.name),
                        description=content.description,
                        other=content.other,
                        fields=self._get_fields(content),
                    )
                    logger.info(
                        f"Данные успешно получены (mode={mode}, value={value!r}, title={get_content.title}, url={str(get_content.url)}, id={get_content.id})",
                        extra={
                            "mode": mode,
                            "value": value,
                            "content": get_content.model_dump(mode="json"),
                        },
                    )
                    return get_content

                logger.debug(
                    f"Контент не найден (mode={mode}, value={value!r})",
                    extra={"mode": mode, "value": value},
                )
                return

        except Exception:
            logger.exception(
                f"Ошибка при получении данных из БД (mode={mode}, value={value!r})",
                extra={"mode": mode, "value": value},
            )
            raise

    async def change_content(
        self, mode: Literal["id", "url"], value: int | str, change: ChangeSchema
    ) -> GetContent:
        """Изменить обьект

        Args:
            mode (Literal[&quot;id&quot;, &quot;url&quot;]): Режим поиска
            value (int | str): Значение для поиска
            change (ChangeSchema): Изменяемая схема

        Raises:
            ValueError: Если не найде обьект для изменение

        Returns:
            GetContent: Обьект данных из БД
        """
        logger.debug(
            f"Попытка изменить объект (mode={mode}, value={value!r}, title={change.title}, url={str(change.url)})",
            extra={
                "mode": mode,
                "value": value,
                "change": change.model_dump(mode="json"),
            },
        )
        try:
            async with self.begin() as session:
                if not (content := await self._get_content(session, mode, value)):
                    logger.error(
                        f"Объект для изменения не найден (mode={mode}, value={value!r})",
                        extra={"mode": mode, "value": value},
                    )
                    raise ValueError("Не найдено обьект для изменение")

                change_template = change.model_dump(exclude_unset=True)

                fields: dict[str, list[str]] = change_template.pop("fields", {})
                tag: str | None = change_template.pop("tag", None)
                field_result: dict[str, list[DataField]] = self._get_fields(content)

                logger.debug(
                    f"Поля для отдельной обработки: fields={list(fields.keys())}, tag={tag}",
                    extra={"fields_to_update": fields, "tag_to_update": tag},
                )

                if fields:
                    logger.debug(
                        f"Попытка получить все теги для изменяемых полей (fields={list(fields.keys())})",
                        extra={"fields": fields},
                    )
                    content.fields = [
                        await self._get_tag(
                            session,
                            Field,
                            field_key,
                            tag=await self._get_tag(session, FieldTag, key),
                        )
                        for key, fields in fields.items()
                        for field_key in fields
                    ]
                    field_result = self._get_fields(content)
                    logger.debug(
                        f"Все теги полей получены и применены (fields={list(fields.keys())}, db_fields={list(field_result.keys())})",
                        extra={
                            "requested_fields": fields,
                            "db_fields": {
                                outer_key: [
                                    {"name": f.name, "id": f.id} for f in fields_list
                                ]
                                for outer_key, fields_list in field_result.items()
                            },
                        },
                    )

                if tag:
                    logger.debug(f"Попытка получить новый тег контента (tag={tag!r})")
                    content_tag = await self._get_tag(session, ContentTag, tag)
                    content.tag = content_tag
                    logger.debug(
                        f"Тег контента обновлён (old_tag_id={content.tag.id if hasattr(content, 'tag') else 'N/A'}, new_tag={content_tag.name!r}, new_tag_id={content_tag.id})",
                        extra={
                            "new_tag_id": content_tag.id,
                            "new_tag_name": content_tag.name,
                        },
                    )

                if change_template:
                    logger.debug(
                        f"Применение оставшихся изменений к атрибутам: {list(change_template.keys())}",
                        extra={"attributes_to_change": change_template},
                    )
                    for key, attr_value in change_template.items():
                        setattr(
                            content,
                            key,
                            attr_value
                            if not isinstance(attr_value, HttpUrl)
                            else str(attr_value),
                        )
                    logger.debug(
                        f"Атрибуты успешно изменены (updated_keys={list(change_template.keys())})",
                        extra={"updated_keys": list(change_template.keys())},
                    )

                else:
                    logger.debug("Нет дополнительных атрибутов для изменения")

                await session.flush()
                get_content = GetContent(
                    id=content.id,
                    title=content.title,
                    url=content.url,
                    poster=content.poster,
                    tag=DataField(id=content.tag.id, name=content.tag.name),
                    description=content.description,
                    other=content.other,
                    fields=field_result,
                )
                logger.info(
                    f"Объект успешно изменён (mode={mode}, value={value!r}, title={get_content.title}, url={str(get_content.url)}, id={get_content.id}))",
                    extra={
                        "mode": mode,
                        "value": value,
                        "updated_content": get_content.model_dump(mode="json"),
                    },
                )
                return get_content

        except Exception as e:
            logger.exception(
                f"Ошибка при изменении объекта в БД (mode={mode}, value={value!r}, exception={e!r})",
                extra={
                    "mode": mode,
                    "value": value,
                    "change": change.model_dump(mode="json"),
                    "exception": str(e),
                },
            )
            raise

    async def delete_content(
        self, mode: Literal["id", "url"], value: int | str
    ) -> bool:
        """Удалить обьект из БД

        Args:
            mode (Literal[&quot;id&quot;, &quot;url&quot;]): Режим поиска
            value (int | str): Значение для поиска

        Returns:
            bool: Если удалось удалить обьект иначе False
        """
        logger.debug(
            f"Попытка удалить объект (mode={mode}, value={value!r})",
            extra={"mode": mode, "value": value},
        )
        try:
            async with self.begin() as session:
                logger.debug(
                    f"Выполнение запроса к БД для поиска удаляемого объекта (mode={mode}, value={value!r})"
                )
                content = await self._get_content(session, mode, value)
                logger.debug(
                    f"Запрос к БД завершён (mode={mode}, value={value!r}, found={content is not None})",
                    extra={"mode": mode, "value": value, "found": content is not None},
                )

                if not content:
                    logger.debug(
                        f"Объект для удаления не найден (mode={mode}, value={value!r})",
                        extra={"mode": mode, "value": value},
                    )
                    return False

                logger.debug(
                    f"Объект найден, выполняется удаление (content_id={content.id})",
                    extra={"content_id": content.id},
                )
                await session.delete(content)
                await session.flush()

                logger.info(
                    f"Объект успешно удалён (mode={mode}, value={value!r}, deleted_content_id={content.id})",
                    extra={
                        "mode": mode,
                        "value": value,
                        "deleted_content_id": content.id,
                    },
                )
                return True

        except Exception as e:
            logger.exception(
                f"Ошибка при удалении объекта из БД (mode={mode}, value={value!r}, exception={e!r})",
                extra={"mode": mode, "value": value, "exception": str(e)},
            )
            raise

    async def random_content(self, tag: str | None = None) -> GetContent:
        """Получить рандомный контент

        Args:
            tag (str | None, optional): В каком теге будет происходить поиск

        Returns:
            GetContent: Контент
        """
        try:
            options = [
                joinedload(Content.tag),
                selectinload(Content.fields).joinedload(Field.tag),
            ]
            base_stmt = select(Content)

            if tag:
                base_stmt = base_stmt.join(Content.tag).where(ContentTag.name == tag)

            base_stmt = base_stmt.order_by(func.random()).limit(1).options(*options)

            async with self.session() as session:
                content = await session.scalar(base_stmt)

                if not content:
                    raise ValueError(
                        "БД пуста `ಠ_ಠ` серьёзно?"  # NOTE: Шуточная ошибка, поменять на более информативную
                    )

                return GetContent(
                    id=content.id,
                    title=content.title,
                    url=content.url,
                    poster=content.poster,
                    tag=DataField(id=content.tag.id, name=content.tag.name),
                    description=content.description,
                    other=content.other,
                    fields=self._get_fields(content),
                )

        except Exception:
            logger.exception("Ошибка при получении рандомного контента из БД")
            raise

    @asynccontextmanager
    async def connect(self) -> AsyncGenerator[_FastConnection]:
        async with self.session() as session:
            yield _FastConnection(session)

    @staticmethod
    async def _get_tag(
        session: AsyncSession, tag_type: type[_T], value: str, **kwargs
    ) -> _T:
        stmt = select(tag_type).where(tag_type.name == value)
        if issubclass(tag_type, Field):
            stmt = stmt.options(joinedload(Field.tag))

        if _tag := await session.scalar(stmt):
            return _tag

        _tag = tag_type(name=value, **kwargs)

        session.add(_tag)
        await session.flush()

        return _tag

    @staticmethod
    async def _get_content(
        session: AsyncSession, mode: Literal["id", "url"], value: int | str
    ) -> Content | None:
        options = [
            joinedload(Content.tag),
            selectinload(Content.fields).joinedload(Field.tag),
        ]

        if mode == "id":
            return await session.get(Content, value, options=options)

        else:
            stmt = (
                select(Content).options(*options).where(getattr(Content, mode) == value)
            )
            return await session.scalar(stmt)
