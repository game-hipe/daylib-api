from __future__ import annotations

import asyncio
import json
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from celery.contrib.abortable import AbortableAsyncResult
from loguru import logger

from ._status import (
    SpiderStatus,
    SpiderStatusSnapshot,
    ACTIVE_STATES,
    END_STATES,
    TaskState,
)
from ._typing import SPIDER
from ._worker import Worker

if TYPE_CHECKING:
    from ...abstract.spider import BaseSpider
    from ...abstract.spider._status import SpiderParsingStatus
    from ...manager.database.model import ModelManager
    from ...manager.alert import AlertManager, LEVEL


class _StateStorage:
    def __init__(self, path: Path):
        """Хранилище состояний пауков

        Args:
            path (Path): Путь к файлу со снапшотами
        """
        self.path = path
        self._lock = asyncio.Lock()

    def load(self) -> list[SpiderStatusSnapshot]:
        """Загрузить все снапшоты в память

        Returns:
            list[SpiderStatusSnapshot]: Последнее состояние пауков
        """
        if not self.path.exists():
            return []

        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as error:
            logger.warning(
                "Не удалось загрузить сохранённое состояние задач: %s. Файл будет перезаписан.",
                error,
            )
            return []

    async def save(self, snapshots: list[SpiderStatusSnapshot]) -> None:
        """Сохранить файл со снапшотами.

        Args:
            snapshots (list[SpiderStatusSnapshot]): Последнее состояние пауков
        """
        async with self._lock:
            await asyncio.to_thread(self._write_file, snapshots)

    def _write_file(self, snapshots: list[SpiderStatusSnapshot]) -> None:
        """Создаёт путь к файлу и пишет в файл

        Args:
            snapshots (list[SpiderStatusSnapshot]): Последнее состояние пауков
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(snapshots, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


@dataclass
class TaskRecord:
    spider: "BaseSpider"
    parser_status: SpiderParsingStatus | None
    status: SpiderStatus
    progress_watcher: asyncio.Task | None = None


class TaskManager:
    BASE_BATCH: int = 5
    MAX_RETRIES: int = 3

    def __init__(
        self,
        model: "ModelManager",
        batch: int | None = None,
        alert: AlertManager | None = None,
        use_celery: bool = True,
        max_retries: int | None = None,
        state_file: Path | None = None,
    ):
        """Менеджер задач

        Args:
            model (ModelManager): Модель для взаимодействие с БД
            batch (int | None, optional): Размер пачки, которое будет работать в памяти, но после которого будут отправляться в Celery. По умолчанию None.
            alert (AlertManager | None, optional): Менеджер уведомлений, будет передовать всё что возвращает Celery. По умолчанию None.
            use_celery (bool, optional): Использовать ли Celery, если указан False то Celery не будет использоваться. По умолчанию True.
            max_retries (int | None, optional): Максимальное количество попыток для Celery. По умолчанию None.
            state_file (Path | None, optional): Путь к файлам для сохранение состояние. По умолчанию None.
        """
        self._model = model
        self.batch = batch or self.BASE_BATCH
        self.use_celery = use_celery
        self.max_retries = max_retries or self.MAX_RETRIES
        self._alert = alert
        self._lock = asyncio.Lock()

        self._pending: deque[TaskRecord] = deque()
        self._memory: dict[str, TaskRecord] = {}
        self._celery_tasks: dict[str, AbortableAsyncResult] = {}
        self._status: dict[str, SpiderStatus] = {}
        self._storage = _StateStorage(
            state_file or Path(__file__).resolve().parent.joinpath(".spider_state.json")
        )
        self._load_persisted_state()

    def _load_persisted_state(self) -> None:
        """Загрузить последний снапшот пауков"""
        for snapshot in self._storage.load():
            status = SpiderStatus.from_snapshot(snapshot)
            if status.state in ACTIVE_STATES:
                status.state = "interrupted"
            self._status[status.name] = status

    async def recover(
        self,
        spiders: list["BaseSpider"],
        state: TaskState | Literal["all"] = "interrupted",
    ) -> list[SpiderStatus]:
        """Перезапустить всех пауков которые находятся в `self._status`

        Args:
            spiders (list[&quot;BaseSpider&quot;]): Доступные пауки которые мы можем запустить

        Returns:
            list[SpiderStatus]: Статус всех новых запущеных пауков
        """

        recovered: list[SpiderStatus] = []
        for status in list(self._status.values()):
            if state != "all":
                if status.state != state:
                    continue

            spider = next(
                (item for item in spiders if item.name() == status.name), None
            )
            if spider is None:
                continue

            start_kwargs = status.start_kwargs.copy()
            if status.current_page > 1:
                start_kwargs["start_page"] = status.current_page

            recovered_status = await self.register_task(
                spider,
                force=True,
                **start_kwargs,
            )
            recovered.append(recovered_status)

        return recovered

    async def register_task(
        self,
        spider: "BaseSpider",
        *,
        start_page: int = 1,
        pagination_kwargs: dict | None = None,
        update: bool = False,
        force: bool = False,
        force_memory: bool = False,
        **kwargs,
    ) -> SpiderStatus:
        """Регистрирует задачу.
        Если количество запущеных задач в памяти более чем `batch` то они будут автоматически перенесены в celery.
        Но если `self.use_celery`, будет False, то все задачи будут работать в памяти.
        Так-же если `force_memory`, будет True то задача в том или ином случае будет запускаться в памяти

        Args:
            spider (BaseSpider): Базовый паук, которого нужно запустить
            start_page (int, optional): Стартовая страница для парсинга. По умолчанию 1.
            pagination_kwargs (dict | None, optional): Ключевые параметры для пагинации, для функции :func:`pagination`. По умолчанию None.
            update (bool, optional): Обновлять ли контент если он находится в БД. По умолчанию False.
            force (bool, optional): Создавать ли новую задачу если прошлая работает, найденная задача просто отменяется. По умолчанию False.
            force_memory (bool, optional): Обязательно ли работать в памяти. По умолчанию False.

        Returns:
            SpiderStatus: Статус данной задачи
        """
        name = spider.name()

        async with self._lock:
            existing = self._status.get(name)
            if existing and existing.state in ACTIVE_STATES:
                if not force:
                    return existing

        logger.debug(f"Запуск паука: {name}")
        if existing and existing.state in ACTIVE_STATES:
            logger.info(
                f"Отмена паука перед повторным запуском: {name}"
            )
            await self.stop_task(name)

        start_kwargs = {
            "start_page": start_page,
            "pagination_kwargs": pagination_kwargs,
            "update": update,
            **kwargs,
        }

        status = SpiderStatus(
            name=name,
            start_kwargs=start_kwargs,
            current_page=start_page,
            total_page=1,
            _is_end=False,
            state="pending",
        )

        record = TaskRecord(spider=spider, parser_status=None, status=status)
        self._status[name] = status

        if len(self._memory) >= self.batch:
            if self.use_celery and not force_memory:
                return await self._start_celery_task(spider, status, start_kwargs)

            status.state = "queued"
            self._pending.append(record)
            await self._persist()
            return status

        return await self._start_memory_task(record, start_kwargs)

    async def stop_task(self, spider: SPIDER) -> SpiderStatus:
        """Остановить задачу

        Args:
            spider (SPIDER): Название паука или сам паук

        Raises:
            KeyError: Если искаемый паук не найден нигде
            RuntimeError: Если париснг вообще не запущен
            ValueError: Если не удалось остановить задачу

        Returns:
            SpiderStatus: Статус задачи
        """
        name = spider if isinstance(spider, str) else spider.name()

        async with self._lock:
            record = self._memory.get(name)
            if record is None:
                record = next(
                    (record for record in self._pending if record.status.name == name),
                    None,
                )

            celery_task = self._celery_tasks.get(name)
            status = self._status.get(name)

        if record is None and celery_task is None and status is None:
            raise KeyError(f"Паук `{name}` не найден в очереди задач")

        if record is not None:
            if record in self._pending:
                self._pending.remove(record)
                await record.status.set_state("cancelled")
                await self._persist()
                return record.status

            if not record.parser_status:
                raise RuntimeError("Парсер не запущен.")

            if record.parser_status.task and not record.parser_status.task.done():
                record.parser_status.task.cancel()

            try:
                if record.parser_status.task is not None:
                    await record.parser_status.task
            except asyncio.CancelledError:
                pass

            if (
                record.progress_watcher is not None
                and not record.progress_watcher.done()
            ):
                record.progress_watcher.cancel()

            async with self._lock:
                self._memory.pop(name, None)
                await record.status.set_state("cancelled")
                await self._persist()

            await self._process_queue()
            return record.status

        if celery_task is not None and status is not None:
            try:
                celery_task.abort()
                result = await asyncio.to_thread(celery_task.get, 10)
                if result:
                    for message in result.get("alert", []):
                        await self.alert(**message)
                else:
                    logger.warning("Celery ничего не ввернул")

            except Exception:
                logger.exception(f"Не удалось остановить задачу Celery {name}")

            await status.set_state("cancelled")
            async with self._lock:
                self._celery_tasks.pop(name, None)
                await self._persist()
            return status

        raise ValueError("Не удалось остнановить задачу")

    async def get_status(self) -> list[SpiderStatus]:
        """Получить все статусы"""
        async with self._lock:
            return list(self._status.values())

    async def _start_memory_task(
        self,
        record: TaskRecord,
        start_kwargs: dict[str, Any],
    ) -> SpiderStatus:
        """Начать парсинг внутри памяти

        Args:
            record (TaskRecord): Запись паука
            start_kwargs (dict[str, Any]): Стартовые параметры

        Returns:
            SpiderStatus: Статус задачи
        """
        parser_status = await record.spider.start_parsing(
            manager=self._model,
            **start_kwargs,
        )

        status = record.status
        record.parser_status = parser_status
        status.task = parser_status.task
        status.state = "running"
        status.current_page = parser_status.current_page
        status.total_page = parser_status.total_page

        async with self._lock:
            self._memory[status.name] = record

        record.progress_watcher = asyncio.create_task(
            self._memory_task_listener(record)
        )
        parser_status.task.add_done_callback(
            lambda task, name=status.name: asyncio.create_task(
                self._memory_task_done(name, task)
            )
        )

        await self._persist()
        return status

    async def _start_celery_task(
        self,
        spider: "BaseSpider",
        status: SpiderStatus,
        start_kwargs: dict[str, Any],
    ) -> SpiderStatus:
        """Запустить Celery задачу

        Args:
            spider (BaseSpider): Паук которого мы должны запустить в Celery
            status (SpiderStatus): Ссылка на статус для обновление ситуации Celery таска
            start_kwargs (dict[str, Any]): Стартовые параметры

        Returns:
            SpiderStatus: Статус задачи
        """
        try:
            task = await asyncio.to_thread(
                Worker.start_spiders.delay,
                spiders=[spider.name()],
                clients=[spider.client.name],
                spider_snapshot={spider.name(): start_kwargs},
                extra_kwargs={
                    spider.name(): {
                        key: value
                        for key, value in spider.kwargs.items()
                        if key != "alert"
                    }
                },
                client_kwargs={spider.client.name: spider.client.config},
            )
        except RuntimeError:
            logger.exception("Celery не доступен")
            raise

        status.task = task
        status.task_id = task.id
        status.state = "queued"

        async with self._lock:
            self._celery_tasks[status.name] = task

        asyncio.create_task(self._celery_task_listener(task, status))
        await self._persist()
        return status

    async def _memory_task_listener(self, record: TaskRecord) -> None:
        """Слушать задачу которая крутится в памяти

        Args:
            record (TaskRecord): Запись об задаче
        """
        try:
            while not record.parser_status.is_end:
                await record.status.update(
                    current_page=record.parser_status.current_page,
                    total_page=record.parser_status.total_page,
                    is_end=record.parser_status.is_end,
                )
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            await record.status.update(
                current_page=record.parser_status.current_page,
                total_page=record.parser_status.total_page,
                is_end=record.parser_status.is_end,
            )

    async def _memory_task_done(self, name: str, task: asyncio.Task) -> None:
        """Действие после того как задача будет выполнена в памяти

        Args:
            name (str): Название паука
            task (asyncio.Task): Задача asyncio для получениеи его статуса, и причины ошибки при необходимости
        """
        async with self._lock:
            record = self._memory.pop(name, None)

        if record is None:
            return

        if record.progress_watcher is not None and not record.progress_watcher.done():
            record.progress_watcher.cancel()

        if task.cancelled():
            await record.status.set_state("cancelled")
        elif task.exception() is not None:
            await record.status.set_state("failed", error=str(task.exception()))
        else:
            await record.status.set_state("completed")

        await record.status.update(
            current_page=record.parser_status.current_page,
            total_page=record.parser_status.total_page,
            is_end=record.parser_status.is_end,
        )

        await self._persist()
        await self._process_queue()

    async def _celery_task_listener(
        self, task: AbortableAsyncResult, status: SpiderStatus
    ) -> None:
        """Слушать задачу Celery

        Args:
            task (AbortableAsyncResult): Результат Celery
            status (SpiderStatus): Статус паука для обновление ситуации
        """
        exception_count = 0

        try:
            while not task.ready():
                state = task.state or "PENDING"
                if state == "STARTED":
                    await status.set_state("running")
                elif state in {"PENDING", "RECEIVED", "RETRY"}:
                    await status.set_state("queued")
                elif state == "REVOKED":
                    await status.set_state("cancelled")
                    return

                info = task.info or {}
                if state == "RETRY":
                    exception_count += 1
                    if exception_count >= self.max_retries:
                        logger.warning(
                            f"Не удалось достучаться до {task.id!r}, паук утерян: {status.name!r}",
                            meta={"task_id": task.id, "spider": status.name},
                        )
                        await self.alert(
                            f"Не удалось достучаться до {task.id!r}, паук утерян: {status.name!r}",
                            level="warning",
                        )

                        await status.set_state(
                            "failed",
                            error="Превышено количество повторов задачи Celery",
                        )
                        return

                if isinstance(info, dict):
                    current_page = (
                        info.get("status", {}).get(status.name, {}).get("current_page")
                    )
                    total_page = (
                        info.get("status", {}).get(status.name, {}).get("total_page")
                    )
                    is_end = info.get("status", {}).get(status.name, {}).get("is_end")

                    if (
                        current_page is not None
                        or total_page is not None
                        or is_end is not None
                    ):
                        await status.update(
                            current_page=current_page,
                            total_page=total_page,
                            is_end=is_end,
                        )

                    for alert in info.get("alert", []):
                        await self.alert(**alert)

                await asyncio.sleep(1)

            info = await asyncio.to_thread(task.get, 10)
            if info is not None:
                for alert in info.get("alert", []):
                    await self.alert(**alert)

            if task.state == "REVOKED":
                await status.set_state("cancelled")
            elif task.failed():
                error = None
                try:
                    error = str(task.result)
                except Exception:
                    error = "Неизвестная ошибка Celery"
                await status.set_state("failed", error=error)
            else:
                await status.set_state("completed")

            if isinstance(task.info, dict):
                current_page = (
                    task.info.get("status", {}).get(status.name, {}).get("current_page")
                )
                total_page = (
                    task.info.get("status", {}).get(status.name, {}).get("total_page")
                )
                is_end = task.info.get("status", {}).get(status.name, {}).get("is_end")
                await status.update(
                    current_page=current_page, total_page=total_page, is_end=is_end
                )

        except asyncio.CancelledError:
            pass
        finally:
            async with self._lock:
                self._celery_tasks.pop(status.name, None)
            await self._persist()

    async def _process_queue(self) -> None:
        """
        Начать новую задачу в памяти если появится место
        """
        while len(self._memory) < self.batch and self._pending:
            record = self._pending.popleft()
            if record.status.state in END_STATES:
                continue
            await self._start_memory_task(record, record.status.start_kwargs)

    async def _persist(self) -> None:
        """Сохранять состояние пауков"""
        snapshots = [status.to_snapshot() for status in self._status.values()]
        await self._storage.save(snapshots)

    async def alert(self, message: str, level: LEVEL):
        """Вспомогательная функция для отправки уведомлений если :class:`AlertManager` передан

        Args:
            message (str): _description_
            level (LEVEL): _description_
        """
        if self._alert:
            await self._alert.send_message(message, level)
