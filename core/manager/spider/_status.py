from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Self, TypedDict
from asyncio import Task

from celery.result import AsyncResult
from pydantic import BaseModel

TaskMode = Literal["memory", "celery"]
TaskState = Literal[
    "pending",
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
    "interrupted",
    "idle",
]

END_STATES = {"completed", "failed", "cancelled", "interrupted"}
ACTIVE_STATES = {"pending", "queued", "running"}


class SpiderStatusSnapshot(TypedDict, total=False):
    name: str
    start_kwargs: dict[str, Any]
    state: TaskState
    current_page: int
    total_page: int
    is_end: bool
    error: str | None
    task_id: str
    created_at: str
    updated_at: str


class SpiderStatusSnapshotSchema(BaseModel):
    name: str = ""
    start_kwargs: dict[str, Any] = {}
    state: TaskState = "idle"
    current_page: int = 0
    total_page: int = 0
    is_end: bool = False
    error: str | None = None
    task_id: str = ""
    created_at: str = datetime.now().isoformat()
    updated_at: str = datetime.now().isoformat()


@dataclass
class SpiderStatus:
    name: str
    start_kwargs: dict[str, Any] = field(default_factory=dict)
    current_page: int = 1
    total_page: int = 1
    _is_end: bool = False
    state: TaskState = "pending"
    error: str | None = None
    task: Task | AsyncResult | None = None
    task_id: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    end: asyncio.Event = field(default_factory=asyncio.Event, init=False)

    def __post_init__(self) -> None:
        if self.state in END_STATES or self._is_end:
            self.end.set()

    @property
    def mode(self) -> TaskMode:
        """Режим в котором находится статус"""
        return "memory" if not isinstance(self.task, AsyncResult) else "celery"

    @property
    def is_end(self) -> bool:
        """Указывает конец ли это или нет"""
        return (
            self.state in END_STATES
            or self._is_end
            or (self.task.done() if isinstance(self.task, Task) else False)
        )

    async def update(
        self,
        current_page: int | None = None,
        total_page: int | None = None,
        is_end: bool | None = None,
    ) -> None:
        """Обновить статус

        Args:
            current_page (int | None, optional): Текущая страница. По умолчанию None.
            total_page (int | None, optional): Общее количество найденных страниц. По умолчанию None.
            is_end (bool | None, optional): Флаг конца. По умолчанию None.
        """
        if current_page is not None and current_page > self.current_page:
            self.current_page = current_page

        if total_page is not None and total_page != self.total_page:
            self.total_page = total_page

        if is_end is not None:
            self._is_end = is_end

        self.updated_at = datetime.utcnow()
        if self.state in END_STATES or self.is_end:
            self.end.set()

    async def set_state(self, state: TaskState, error: str | None = None) -> None:
        """Установить состояние для статуса

        Args:
            state (TaskState): состояние
            error (str | None, optional): Ошибка которое могло произойти. По умолчанию None.
        """
        self.state = state
        self.error = error
        self.updated_at = datetime.utcnow()
        if self.state in END_STATES:
            self.end.set()

    async def wait_for_end(self) -> None:
        """Ждать до конца задачи"""
        await self.end.wait()

    def to_snapshot(self) -> SpiderStatusSnapshot:
        """Превратить статус в снапшот

        Returns:
            SpiderStatusSnapshot: снапшот
        """
        snapshot: SpiderStatusSnapshot = {
            "name": self.name,
            "start_kwargs": self.start_kwargs.copy(),
            "state": self.state,
            "current_page": self.current_page,
            "total_page": self.total_page,
            "is_end": self.is_end,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
        if self.task_id:
            snapshot["task_id"] = self.task_id
        return snapshot

    @classmethod
    def from_snapshot(cls, snapshot: SpiderStatusSnapshot) -> Self:
        """Инцилизировать статус из снапшота

        Args:
            snapshot (SpiderStatusSnapshot): Снапшот

        Returns:
            SpiderStatus: Статус
        """
        status = cls(
            name=snapshot["name"],
            start_kwargs=snapshot.get("start_kwargs", {}).copy(),
            current_page=snapshot.get("current_page", 1),
            total_page=snapshot.get("total_page", 1),
            _is_end=snapshot.get("is_end", False),
            state=snapshot.get("state", "pending"),
            error=snapshot.get("error"),
        )
        status.created_at = datetime.fromisoformat(
            snapshot.get("created_at", status.created_at.isoformat())
        )
        status.updated_at = datetime.fromisoformat(
            snapshot.get("updated_at", status.updated_at.isoformat())
        )
        status.task_id = snapshot.get("task_id")
        if status.state in END_STATES or status.is_end:
            status.end.set()
        return status
