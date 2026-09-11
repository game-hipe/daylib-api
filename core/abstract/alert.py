from abc import ABC, abstractmethod
from typing import Literal

type LEVEL = Literal["debug", "info", "warning", "error"]


class BaseAlert(ABC):
    def __init__(self, delete: bool = False):
        """Инициализация системы оповещений

        Args:
            delete (bool, optional): Удаляит ли при неудачной попытке отправить сообщение. По умолчанию False.
        """
        self.delete = delete

    @abstractmethod
    async def alert(self, message: str, level: LEVEL, **kwargs) -> bool:
        """Оповещение

        Args:
            message (str): сообщение
            level (Literal[&quot;debug&quot;, &quot;info&quot;, &quot;warning&quot;, &quot;error&quot;]): уровень сообщение

        Returns:
            bool: Удалось ли отправить сообщение
        """

    @classmethod
    def name(cls) -> str:
        return cls.__name__
