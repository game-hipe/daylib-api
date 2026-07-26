from contextlib import asynccontextmanager

from aiohttp import ClientResponse, ClientSession

from ...abstract.client import BaseClient
from ...exception import StatusCodeException


class AiohttpClient(BaseClient[ClientSession, ClientResponse]):
    @asynccontextmanager
    async def _request(
        self, url, method=None, proxy=None, raise_for_status=True, **kwargs
    ):
        kwargs["proxy"] = kwargs.get("proxy", proxy)
        async with self.session.request(
            method or "GET", url, **kwargs, allow_redirects=True
        ) as response:
            if not response.ok and raise_for_status:
                raise StatusCodeException(url=url, status=response.status, client=self)
            yield response

    @classmethod
    async def load(cls, config=None, **kwargs):
        config = config or {}

        session = ClientSession(**kwargs)
        return cls(session, **config)

    async def __aexit__(self, exc_type, exc, tb):
        await self._session.close()
