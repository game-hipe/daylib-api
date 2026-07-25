from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .abstract.client import BaseClient


class _BaseException(Exception):
    """Базовая ошибка"""

    ERROR_TEXT: str = ""

    def __init__(self, *args):
        self.message = ", ".join(args).strip()

    def __str__(self):
        return f"{self.ERROR_TEXT}{'.' if self.message else ''} {self.message}".strip()

    @property
    def name(self) -> str:
        return self.__class__.__name__

    def error(self) -> str:
        cols = self.__init__.__annotations__
        values = {col: getattr(self, col) for col in cols}
        return f"Ошибка: {str(self)} ({', '.join(f'{k}={v!r}' for k, v in values.items())})"


class ClientException(_BaseException):
    """Ошибка клиента"""

    ERROR_TEXT = "Неизвестная ошибка связанная с клиентом"

    def __init__(self, client: "BaseClient", *args):
        super().__init__(*args)
        self.client = client


class RequestException(ClientException):
    """Ошибка во время запроса"""

    ERROR_TEXT = "Ошибка во время запроса"

    def __init__(self, url: str, client: "BaseClient", *args):
        super().__init__(client, *args)
        self.url = url


class ResponseException(ClientException):
    """Ошибка во время ответа"""

    ERROR_TEXT = "Ошибка в ответе запроса"

    def __init__(self, url: str, status: int, client: "BaseClient", *args):
        super().__init__(client, *args)
        self.url = url
        self.status = status


class StatusCodeException(ResponseException):
    """Ошибка связанная со статусом"""

    ERROR_TEXT = "Сервис вернул неожиданный код ответа"


class MaxAttemtException(RequestException):
    """Ошибка которая указывает на максимальное колличество попыток"""

    ERROR_TEXT = "Максимальное количество попыток исчерпано"

    def __init__(self, url: str, max_try: int, client: "BaseClient", *args):
        super().__init__(url, client, *args)
        self.max_try = max_try


class SpiderException(_BaseException):
    """Базовая ошибка паука"""

    ERROR_TEXT = "Неизвестная ошибка во время работы паука"


class ParseError(SpiderException):
    """Ошибка связанная с парсингом"""

    ERROR_TEXT = "Ошибка во время парсинга"


class RequiredObjNotFoundException(ParseError):
    """Ошибка если необходимый обьект не найден"""

    ERROR_TEXT = "Необходимый обьект не найден"
