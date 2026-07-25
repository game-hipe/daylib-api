import asyncio

from sqlalchemy.ext.asyncio import create_async_engine
from loguru import logger
from uvicorn import Config, Server
from dotenv import load_dotenv

from core.manager.database import ModelManager, SearchManager
from core.manager.client import AiohttpClient, PatchrightClient
from core.manager.spider import SpiderManager
from core.manager.alert import AlertManager
from api.app import ContentAPI

from core._log import init
from core.config import setting

init()
load_dotenv()


async def main():
    engine = create_async_engine(setting.database_url_async)
    try:
        alert = AlertManager()
        async with (
            await AiohttpClient.load() as client,
            await PatchrightClient.load() as browser,
        ):
            model = ModelManager(engine)
            api = ContentAPI(
                model=model,
                alert=alert,
                search=SearchManager(engine),
                spider=SpiderManager(
                    clients=[client, browser], model=model, alert=alert
                ),
            )
            server = Server(
                config=Config(app=api.app, host=setting.host_api, port=setting.port_api)
            )
            await server.serve()

    finally:
        await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        logger.info("задача убита пользователем")
