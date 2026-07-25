import math
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import Select, exists, select, or_, and_, func

from ._db import _BaseManager
from ...entitie import (
    Content,
    PaginationSchema,
    ContentTag,
    Field,
    GetContent,
    DataField,
    FieldTag,
    ConnnectionFC,
)


class SearchManager(_BaseManager):
    async def _get_all(self, stmt: Select[tuple[Content]]) -> int:
        """Считать общее количество обьектов

        Args:
            stmt (Select[tuple[Content]]): Базовый запрос

        Returns:
            int: Общее количество предметов по запросу
        """
        async with self.session() as session:
            count_stmt = select(func.count()).select_from(stmt.subquery())
            return await session.scalar(count_stmt)

    async def _search(
        self,
        base_stmt: Select[tuple[Content]],
        page: int,
        limit: int,
        session: AsyncSession,
    ) -> PaginationSchema:
        """Базовый поиск с пагинацией

        Args:
            base_stmt (Select[tuple[Content]]): Базовый запрос
            page (int): Номер страницы
            limit (int): Лимит на стрнице
            session (AsyncSession): Асинхронная сессия

        Returns:
            PaginationSchema: Схема пагинации
        """
        stmt = (
            base_stmt.offset(limit * (page - 1))
            .limit(limit)
            .options(
                selectinload(Content.tag),
                selectinload(Content.fields).joinedload(Field.tag),
            )
        )

        contents, total = await asyncio.gather(
            session.scalars(stmt), self._get_all(base_stmt)
        )

        items: list[GetContent] = []
        for content in contents:
            items.append(
                GetContent(
                    id=content.id,
                    title=content.title,
                    url=content.url,
                    poster=content.poster,
                    tag=DataField(id=content.tag.id, name=content.tag.name),
                    description=content.description,
                    other=content.other,
                    fields=self._get_fields(content),
                )
            )

        return PaginationSchema(
            current_page=1,
            total_page=math.ceil(total / limit),
            total_items=total,
            items=items,
        )

    async def search(
        self, tag: str | None = None, page: int = 1, limit: int = 15
    ) -> PaginationSchema:
        """Искать по всей БД, с фильтром по тегу

        Args:
            tag (str | None, optional): Тег для поиска. По умолчанию None.
            page (int, optional): Страница. По умолчанию 1.
            limit (int, optional): Количество обьектов на лимите. По умолчанию 15.

        Returns:
            PaginationSchema: Схема пагинации
        """
        async with self.session() as session:
            stmt = select(Content).join(Content.tag)
            if tag is not None:
                stmt = stmt.where(ContentTag.name == tag)

            return await self._search(stmt, page, limit, session)

    async def search_by_title(
        self, text: str, tag: str | None = None, page: int = 1, limit: int = 15
    ) -> PaginationSchema:
        """Искать по названию

        Args:
            text (str): Текст для поиска
            tag (str | None, optional): Тег для поиска. По умолчанию None.
            page (int, optional): Страница. По умолчанию 1.
            limit (int, optional): Количество обьектов на лимите. По умолчанию 15.

        Returns:
            PaginationSchema: Схема пагинации
        """
        async with self.session() as session:
            conditions = [
                or_(
                    Content.title.ilike(f"%{text}%"),
                    Content.description.ilike(f"%{text}%"),
                )
            ]

            if tag is not None:
                conditions.append(ContentTag.name == tag)

            stmt = select(Content).join(Content.tag).where(and_(*conditions))

            return await self._search(stmt, page, limit, session)

    async def search_by_fields(
        self,
        fields: dict[str, list[str]],
        tag: str | None = None,
        strict_mode: bool = True,
        page: int = 1,
        limit: int = 15,
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

        Args:
            fields (dict[str, list[str]]): Заполнение
            tag (str | None, optional): Тег для поиска. По умолчанию None.
            strict_mode (bool, optional): Строгий режим ищет только те произведение у которых есть все заполнение. По умолчанию True.
            page (int, optional): Страница. По умолчанию 1.
            limit (int, optional): Количество обьектов на лимите. По умолчанию 15.

        Returns:
            PaginationSchema: Схема пагинации
        """
        base_stmt = select(Content)

        if tag is not None:
            base_stmt = base_stmt.join(Content.tag).where(ContentTag.name == tag)

        for tag_name, field_names in fields.items():

            def make_subquery(values):
                return (
                    select(1)
                    .select_from(ConnnectionFC)
                    .join(Field, Field.id == ConnnectionFC.field_id)
                    .join(FieldTag, FieldTag.id == Field.tag_id)
                    .where(
                        ConnnectionFC.content_id == Content.id,
                        FieldTag.name == tag_name,
                        Field.name.in_(values),
                    )
                )

            if strict_mode:
                for value in field_names:
                    sub = make_subquery([value])
                    base_stmt = base_stmt.where(exists(sub))

            else:
                sub = make_subquery(field_names)
                base_stmt = base_stmt.where(exists(sub))

        async with self.session() as session:
            return await self._search(base_stmt, page, limit, session)

    async def search_by_field(
        self,
        field: str,
        value: str | list[str],
        tag: str | None = None,
        page: int = 1,
        limit: int = 15,
    ) -> PaginationSchema:
        """Искать с помошью заполнение

        Args:
            field (str): Ключ для заполнение
            value (str | list[str]): значение для ключа
            tag (str | None, optional): Необходимый тэг. По умолчанию None.
            page (int, optional): Страница. По умолчанию 1.
            limit (int, optional): Количество обьектов на лимите. По умолчанию 15.

        Returns:
            PaginationSchema: Схема пагинации
        """
        return await self.search_by_fields(
            fields={field: [value] if isinstance(value, str) else value},
            tag=tag,
            strict_mode=False,
            page=page,
            limit=limit,
        )

    def _make_subquery(values: list[str], tag_name: str):
        return (
            select(1)
            .select_from(ConnnectionFC)
            .join(Field, Field.id == ConnnectionFC.field_id)
            .join(FieldTag, FieldTag.id == Field.tag_id)
            .where(
                ConnnectionFC.content_id == Content.id,
                FieldTag.name == tag_name,
                Field.name.in_(values),
            )
        )
