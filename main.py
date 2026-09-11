import asyncio

from dotenv import load_dotenv
from loguru import logger
from sqlalchemy.ext.asyncio import create_async_engine
from uvicorn import Config, Server

from api.app import ContentAPI
from core._log import init
from core.config import setting
from core.manager.alert import AlertManager
from core.manager.client import AiohttpClient, PatchrightClient
from core.manager.database import ModelManager, SearchManager
from core.manager.spider import SpiderManager

init()
load_dotenv()


async def main():
    engine = create_async_engine(setting.database.url)
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
                config=Config(app=api.app, host=setting.api.host, port=setting.api.port)
            )
            await server.serve()

    finally:
        await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        logger.info("задача убита пользователем")
