from core.exception import (
    MaxAttemtException,
    RequestException,
    StatusCodeException,
    _BaseException,
)


class DummyClient:
    pass


def test_base_exception():
    exc = _BaseException("one", "two")
    assert str(exc) == ". one, two"
    assert exc.name == "_BaseException"
    assert "Ошибка:" in exc.error()


def test_status_code_exception():
    client = DummyClient()
    exc = StatusCodeException("https://example.com", 403, client, "blocked")

    assert exc.url == "https://example.com"
    assert exc.status == 403
    assert exc.client is client
    assert "403" in exc.error()


def test_max_attempt_exception():
    client = DummyClient()
    exc = MaxAttemtException("https://example.com", 3, client, "too many tries")

    assert exc.url == "https://example.com"
    assert exc.max_try == 3
    assert exc.client is client
    assert isinstance(exc, RequestException)