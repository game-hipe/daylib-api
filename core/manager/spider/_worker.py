import sys
import asyncio

from typing import TYPE_CHECKING, AsyncGenerator, Any
from contextlib import asynccontextmanager
from importlib import import_module
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine
from celery.contrib.abortable import AbortableTask
from redis.asyncio import Redis
from loguru import logger

if TYPE_CHECKING:
    from ...abstract.client import BaseClient
    from ...abstract.spider import BaseSpider
    from ...abstract.spider import SpiderParsingStatus

from ...config import setting
from ..._celery import load_celery
from ._load import load_spider
from ..database.model import ModelManager
from ...abstract.alert import BaseAlert
from ..alert import AlertManager

app = load_celery("spiders")

engine = create_async_engine(setting.database_url_async)
model = ModelManager(engine)


class AlertListener(BaseAlert):
    def __init__(self, delete=False):
        super().__init__(delete)

        self._lock = asyncio.Lock()
        self._messages: list[dict] = []

    async def alert(self, message, level, **kwargs):
        self._messages.append({"message": message, "level": level})
        return True

    async def get(self):
        send_data = self._messages.copy()
        self._messages.clear()

        return send_data


class Worker:
    @staticmethod
    async def _kill_listener(
        task: AbortableTask, status_dict: dict[str, SpiderParsingStatus[BaseSpider]]
    ):
        """Слушает задачу на то что он прерван

        Args:
            task (AbortableTask): Ссылка на задачу, что-бы следить за ней
            status_dict (dict[str, SpiderParsingStatus[BaseSpider]]): Статус всех пауков в данной сессии
        """
        while not task.is_aborted():
            await asyncio.sleep(0.1)

        for status in status_dict.values():
            status.task.cancel()

    @staticmethod
    async def _event_listener(
        redis: Redis, status_dict: dict[str, SpiderParsingStatus[BaseSpider]]
    ):
        """Слушает Backend на наличие запроса на удаление того или иного паука точечно.

        Args:
            task (AbortableTask): Ссылка на задачу, что-бы получать запросы
            status_dict (dict[str, SpiderParsingStatus[BaseSpider]]): Статус всех пауков в данной сессии
            redis (Redis): Слушать задачи от Backend
        """

        while any(not status.is_end for status in status_dict.values()):
            while not await redis.exists("spider:stop"):
                await asyncio.sleep(0.1)

            spider_name = await redis.get("spider:stop")
            if isinstance(spider_name, bytes):
                spider_name = spider_name.decode()

            if not isinstance(spider_name, str):
                continue

            if spider_name not in status_dict:
                continue

            status_dict[spider_name].task.cancel()
            status_dict.pop(spider_name)

    @staticmethod
    async def _status_sender(
        task: AbortableTask,
        status_dict: dict[str, SpiderParsingStatus[BaseSpider]],
        alert: AlertListener,
    ):
        """Отслеживает статусы пауков, и все уведомление которые отправили через :class:`AlertManager`

        Args:
            task (AbortableTask): Ссылка на задачу, что-бы отправлять статус
            status_dict (dict[str, SpiderParsingStatus[BaseSpider]]): Статус всех пауков в данной сессии
            alert (AlertListener): Обьект :class:`AlertListener` который будет отслеживать все увдеомление
        """
        while any(not status.is_end for status in status_dict.values()):
            status = {
                spider.spider.name(): spider.to_dict()
                for spider in status_dict.values()
            }
            logs = await alert.get()

            task.update_state(state="PROGRESS", meta={"status": status, "alert": logs})

            await asyncio.sleep(1)

    @staticmethod
    async def _start_spiders(
        task: AbortableTask,
        status_dict: dict[str, SpiderParsingStatus[BaseSpider]],
        alert: AlertListener,
        redis: Redis,
    ) -> dict[str, Any]:
        """Начать ожидать пауков.
        Запускает все фоновые задачи, и ждёт завершение всех пауков

        Args:
            task (AbortableTask): Ссылка на задачу, что-бы отправлять статус
            status_dict (dict[str, SpiderParsingStatus[BaseSpider]]): Статус всех пауков в данной сессии
            alert (AlertListener): Обьект :class:`AlertListener` который будет отслеживать все увдеомление
            redis (Redis): Обьект что-бы слушать команды от задачи

        Returns:
            dict[str, Any]: Последний результат из всех пауков и уведомлений, идентичен ответу от :func:`_status_sender`
        """
        event_listener = asyncio.create_task(Worker._event_listener(redis, status_dict))
        status_sender = asyncio.create_task(
            Worker._status_sender(task, status_dict, alert)
        )
        asyncio.create_task(Worker._kill_listener(task, status_dict))
        await asyncio.gather(
            *[status.task for status in status_dict.values()],
            event_listener,
            status_sender,
            return_exceptions=True,
        )

        return {
            "status": {
                spider.spider.name(): spider.to_dict()
                for spider in status_dict.values()
            },
            "alert": await alert.get(),
        }

    @asynccontextmanager
    @staticmethod
    async def _load_spdiders(
        spiders: list[str],
        clients: list[str],
        extra_kwargs: dict[str, dict] | None = None,
        general_kwargs: dict | None = None,
        client_kwargs: dict[str, dict] | None = None,
    ) -> AsyncGenerator[list[BaseSpider]]:
        """Загружает все пауки, и клиенты для запросов, что-бы выдать всех необходимых пауков
        Работает как контекстный менеджер, после выхода из with автоматически закрывает всех клиентов которые были загружены.

        Args:
            spiders (list[str]): Необходимые пауки
            clients (list[str]): Клиенты для запросов
            extra_kwargs (dict[str, dict] | None, optional): Ключевые параметры для отдельных пауков. По умолчанию None. Подробнее :func:`load_spider`
            general_kwargs (dict | None, optional): Общие ключевые параметры для всех пауков. По умолчанию None. Подробнее :func:`load_spider`
            client_kwargs (dict[str, dict] | None, optional): Параметры для клиента. По умолчанию None.

        Returns:
            AsyncGenerator[list[BaseSpider]]: Асинхронный менеджер
        """
        client_kwargs = client_kwargs or {}
        client_package = import_module("..client", package=__package__)
        loaded_clients: list[BaseClient] = []

        for client_name in clients:
            client_factory: type[BaseClient] = getattr(client_package, client_name)
            loaded_clients.append(
                await client_factory.load(**client_kwargs.get(client_name, {}))
            )

        loaded_spiders: list[BaseSpider] = load_spider(
            clients=loaded_clients,
            general_kwargs=general_kwargs,
            extra_kwargs=extra_kwargs,
        )

        try:
            yield [spider for spider in loaded_spiders if spider.name() in spiders]

        finally:
            for client in loaded_clients:
                await client.close()

    @staticmethod
    @app.task(bind=True, base=AbortableTask)
    def start_spiders(
        self: AbortableTask,
        spiders: list[str],
        clients: list[str],
        spider_snapshot: dict[str, dict],
        extra_kwargs: dict[str, dict] | None = None,
        general_kwargs: dict | None = None,
        client_kwargs: dict[str, dict] | None = None,
        *,
        logs_dir: str | None = None,
        level: str | None = None,
    ) -> dict[str, Any]:
        """Запустить указанных пауков

        Args:
            spiders (list[str]): Необходимые пауки
            clients (list[str]): Клиенты которые необходимы для загрузки пауков
            spider_snapshot (dict[str, dict]): Момент в которых пауки были остановлены
            extra_kwargs (dict[str, dict] | None, optional): Ключевые параметры для отдельных пауков. По умолчанию None. Подробнее :func:`load_spider`
            general_kwargs (dict | None, optional): Общие ключевые параметры для всех пауков. По умолчанию None. Подробнее :func:`load_spider`
            client_kwargs (dict[str, dict] | None, optional): Параметры для клиента. По умолчанию None.
            logs_dir (str | None, optional): Директория для логов

        Returns:
            dict[str, Any]: Последний результат из всех пауков и уведомлений, идентичен ответу от :func:`_status_sender`
        """

        log_dir = Path(logs_dir or ".logs")
        log_dir.mkdir(parents=True, exist_ok=True)

        level = level or "INFO"
        json_file = log_dir / ".celery_log.json"

        logger.remove()
        logger.add(sys.stdout, level=level)
        logger.add(json_file, level=level, serialize=True)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            return loop.run_until_complete(
                Worker.main(
                    task=self,
                    spiders=spiders,
                    clients=clients,
                    spider_snapshot=spider_snapshot,
                    extra_kwargs=extra_kwargs,
                    general_kwargs=general_kwargs,
                    client_kwargs=client_kwargs,
                )
            )
        finally:
            loop.close()

    @staticmethod
    async def main(
        task: AbortableTask,
        spiders: list[str],
        clients: list[str],
        spider_snapshot: dict[str, dict],
        extra_kwargs: dict[str, dict] | None = None,
        general_kwargs: dict | None = None,
        client_kwargs: dict[str, dict] | None = None,
    ) -> dict[str, Any]:
        """Запустить указанных пауков

        Args:
            task (AbortableTask): Ссылка на задачу, что-бы работать с ней.
            spiders (list[str]): Необходимые пауки
            clients (list[str]): Клиенты которые необходимы для загрузки пауков
            spider_snapshot (dict[str, dict]): Момент в которых пауки были остановлены
            extra_kwargs (dict[str, dict] | None, optional): Ключевые параметры для отдельных пауков. По умолчанию None. Подробнее :func:`load_spider`
            general_kwargs (dict | None, optional): Общие ключевые параметры для всех пауков. По умолчанию None. Подробнее :func:`load_spider`
            client_kwargs (dict[str, dict] | None, optional): Параметры для клиента. По умолчанию None.

        Returns:
            dict[str, Any]: Последний результат из всех пауков и уведомлений, идентичен ответу от :func:`_status_sender`
        """
        alert = AlertListener()
        general_kwargs = general_kwargs or {}
        general_kwargs |= {"alert": AlertManager(alert)}

        async with Redis.from_url(setting.backend) as redis:
            async with Worker._load_spdiders(
                spiders=spiders,
                clients=clients,
                extra_kwargs=extra_kwargs,
                general_kwargs=general_kwargs,
                client_kwargs=client_kwargs,
            ) as aviable_spiders:
                spider_staus: list[SpiderParsingStatus[BaseSpider]] = []

                for spider in aviable_spiders:
                    spider_staus.append(
                        await spider.start_parsing(
                            model, **spider_snapshot.get(spider.name(), {})
                        )
                    )

                return await Worker._start_spiders(
                    task=task,
                    status_dict={
                        status.spider.name(): status for status in spider_staus
                    },
                    alert=alert,
                    redis=redis,
                )
