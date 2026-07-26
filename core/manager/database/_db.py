from collections import defaultdict
from contextlib import asynccontextmanager

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ...entitie import Content, DataField, Field
from ...entitie.model import ContentTag, FieldTag

__all__ = ["_BaseManager"]


class _BaseManager:
    def __init__(self, engine: AsyncEngine, **kwargs):
        self._engine = engine
        self._session = async_sessionmaker(engine)

    @asynccontextmanager
    async def session(self):
        async with self._session() as session:
            yield session

    @asynccontextmanager
    async def begin(self):
        async with self._session() as session, session.begin():
            yield session

    @staticmethod
    def _get_fields(info: list[Field] | Content) -> dict[str, list[DataField]]:
        fields: dict[str, list[DataField]] = defaultdict(list)
        if isinstance(info, Content):
            info = info.fields

        for field in info:
            fields[field.tag.name].append(DataField(id=field.id, name=field.name))

        return fields

    async def _get_content_tag(self) -> list[DataField]:
        async with self.session() as session:
            return [
                DataField.model_validate(x, from_attributes=True)
                for x in await session.scalars(select(ContentTag))
            ]

    async def _get_field_tag(self) -> list[DataField]:
        async with self.session() as session:
            return [
                DataField.model_validate(x, from_attributes=True)
                for x in await session.scalars(select(FieldTag))
            ]
