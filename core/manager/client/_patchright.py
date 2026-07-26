from contextlib import asynccontextmanager

from patchright.async_api import Browser, BrowserContext, Page, async_playwright

from ...abstract.client import BaseClient
from ...exception import StatusCodeException


class PatchrightClient(BaseClient[Browser, Page]):
    @asynccontextmanager
    async def _request(
        self, url, method=None, proxy=None, raise_for_status=True, **kwargs
    ):
        context: BrowserContext | None = None

        try:
            context = await self.session.new_context(proxy=proxy)
            page = await context.new_page()

            response = await page.goto(url, **kwargs)
            if response is not None and not response.ok and raise_for_status:
                raise StatusCodeException(
                    url=url,
                    status=response.status,
                    client=self,
                )

            yield page

        finally:
            if context is not None and not context.is_closed():
                await context.close()

    @classmethod
    async def load(cls, config=None, **kwargs):
        config = config or {}
        p = async_playwright()
        playwright = await p.start()

        browser = await playwright.chromium.launch(**kwargs)
        instance = cls(browser, **config)

        instance._playwright = p
        return instance

    async def __aexit__(self, exc_type, exc, tb):
        if hasattr(self, "_session") and self._session:
            await self._session.close()

        if hasattr(self, "_playwright") and self._playwright:
            await self._playwright.__aexit__()
