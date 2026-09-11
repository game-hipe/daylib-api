from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from loguru import logger

if TYPE_CHECKING:
    from ...abstract.client import BaseClient
    from ...abstract.spider import BaseSpider
    from ..alert import AlertManager
    from ..database.model import ModelManager
    from ._task import TaskState
    from ._typing import SPIDER

from ._load import load_spider
from ._status import SpiderStatus
from ._task import TaskManager


class SpiderManager:
    def __init__(
        self,
        clients: list[BaseClient] | BaseClient,
        model: ModelManager,
        alert: AlertManager | None = None,
        banned_spider: list[type[BaseSpider] | BaseSpider] | None = None,
        extra_kwargs: dict[type[BaseSpider], dict] | None = None,
        *,
        batch: int | None = None,
        use_celery: bool = True,
        max_retries: int | None = None,
        auto_recover: bool = True,
    ):
        """Менеджер пауков

        Args:
            clients (list[BaseClient] | BaseClient): Клиенты для иницализации пауков которые поддерживают код
            model (ModelManager): Модель менеджера для взаимодействие с БД
            alert (AlertManager | None, optional): Менеджер уведомлений. По умолчанию None.
            banned_spider (list[type[BaseSpider]  |  BaseSpider] | None, optional): Забаненные пауки. По умолчанию None.
            extra_kwargs (dict[type[BaseSpider], dict] | None, optional): Ключевые параметры для отдельных пауков. По умолчанию None.
            batch (int | None, optional): Размер пачки, которое будет работать в памяти, но после которого будут отправляться в Celery. По умолчанию None.
            use_celery (bool, optional): Использовать ли Celery, если указан False то Celery не будет использоваться. По умолчанию True.
            max_retries (int | None, optional): Максимальное количество попыток для Celery. По умолчанию None.
            auto_recover (bool, optional): Автоматически ввернуть сохранённых пауков. По умолчанию True.
        """
        self._model = model
        self._task_manager = TaskManager(
            model=model,
            batch=batch,
            alert=alert,
            use_celery=use_celery,
            max_retries=max_retries,
        )
        self._spiders = load_spider(
            clients=clients,
            banned_spider=banned_spider,
            extra_kwargs=extra_kwargs,
            general_kwargs={
                "alert": alert,
            },
        )

        if auto_recover:
            try:
                import asyncio

                asyncio.get_running_loop().create_task(
                    self._task_manager.recover(self._spiders)
                )
            except RuntimeError:
                logger.debug(
                    "Поток событий не запущен, восстановление будет выполнено позже при первом запуске задачи"
                )

    async def start_all_spider(
        self, extra_kwargs: dict[str, dict] | None = None
    ) -> list[SpiderStatus]:
        """Запустить всех пауков размо

        Args:
            extra_kwargs (dict[str, dict] | None, optional): Ключевые параметры для отдельных пауков. По умолчанию None.

        Returns:
            list[SpiderStatus]: Статусы всех запущенных пауков
        """
        extra_kwargs = extra_kwargs or {}
        status: list[SpiderStatus] = []
        for spider in self._spiders:
            status.append(
                await self.start_spider(
                    spider=spider, **extra_kwargs.get(spider.name(), {})
                )
            )
        return status

    async def stop_all_spider(self) -> None:
        """Остнаовить всех пауков"""
        for spider in self._spiders:
            try:
                await self.stop_spider(spider)
            except KeyError, ValueError, RuntimeError:
                pass

    async def start_spider(
        self,
        spider: SPIDER,
        start_page: int = 1,
        pagination_kwargs: dict | None = None,
        update: bool = False,
        force: bool = False,
        **kwargs,
    ) -> SpiderStatus:
        """Запустить паука

        Args:
            spider (SPIDER): Название или сам паука
            start_page (int, optional): Стартовая страница для парсинга. По умолчанию 1.
            pagination_kwargs (dict | None, optional): Ключевые параметры для пагинации, для функции :func:`pagination`. По умолчанию None.
            update (bool, optional): Обновлять ли контент если он находится в БД. По умолчанию False.
            force (bool, optional): Создавать ли новую задачу если прошлая работает, найденная задача просто отменяется. По умолчанию False.

        Returns:
            SpiderStatus: Статус запущенного паука
        """
        spider = self.get_spider(spider)
        status = await self._task_manager.register_task(
            spider,
            start_page=start_page,
            pagination_kwargs=pagination_kwargs,
            update=update,
            force=force,
            **kwargs,
        )
        return status

    async def stop_spider(self, spider: SPIDER) -> SpiderStatus:
        """Остановить паука

        Args:
            spider (SPIDER): Название или сам паука

        Returns:
            SpiderStatus: Статус паука который был прерван
        """
        spider = self.get_spider(spider)
        return await self._task_manager.stop_task(spider)

    async def get_status(self) -> list[SpiderStatus]:
        """Получить статус всех пауков которые были запущены"""

        result = await self._task_manager.get_status()
        _used_name = {x.name for x in result}

        for spider in self._spiders:
            if spider.name() not in _used_name:
                result.append(
                    SpiderStatus(
                        name=spider.name(),
                        state="idle",
                    )
                )

        return result

    async def recover(
        self, state: TaskState | Literal["all"] = "interrupted"
    ) -> list[SpiderStatus]:
        """Перезапустить всех незакноченных пауков"""
        return await self._task_manager.recover(self._spiders, state)

    def get_spider(self, targer: SPIDER) -> BaseSpider:
        """Получить инцилизиррованного паука

        Args:
            targer (SPIDER): Название или сам паука

        Raises:
            ValueError: Если паук не найден

        Returns:
            BaseSpider: Паук
        """
        name = targer if isinstance(targer, str) else targer.name()
        for spider in self._spiders:
            if spider.name() == name:
                return spider

        raise ValueError("Паук не найден")
