# Middleware — что это и как их готовить

Если вы уже читали [SPIDER_TOOL.md](SPIDER_TOOL.md) то знаете про вспомогательные функции паука. Теперь поговорим про Middleware — это прослойка которая встраивается в конвейер и может обрабатывать результаты до того как они попадут в БД. Валидация, логирование, обогащение данных, фильтрация — всё это сюда.

## Что такое Middleware у нас

Middleware это класс-наследник `SpiderMiddleware` с двумя обязательными методами:

- **`_process_result`** — Обработка успешного результата. Может вернуть изменённый результат или `None` что-бы пропустить его.
- **`_handle_error`** — Обработка ошибок. Вызывается если во время прохода по конвейеру что-то упало.

Middleware создаётся автоматически, вам не надо инстанцировать его руками — паук сам это сделает во время `__init__`.

```python
class SpiderMiddleware(ABC, Generic[_T, _R]):
    def __init__(self, spider: _T):
        self._spider = spider
```

Как видим, на вход middleware получает самого паука, так-что у него есть доступ ко всем его свойствам, клиенту, kwargs и т.д.

---

## Как подключить свой Middleware

Есть 3 способа:

### 1. Через `BASE_MIDDLEWARE` у паука

```python
class MySpider(BaseSpider[AiohttpClient, dict]):
    BASE_MIDDLEWARE = [MyMiddleware, OtherMiddleware]
```

Можно указать как один класс, так и список. Это базовые middleware для конкретного паука.

### 2. Через `middleware` в `__init__`

```python
spider = MySpider(
    client=client,
    middleware=[MyMiddleware],
)
```

Тоже принимает либо один класс, либо список.

### 3. Отключить вообще

```python
spider = MySpider(client=client, use_middleware=False)
```

Тогда `start_parsing_generator` будет работать без обёрток.

---

## Порядок важен

Внутри `__init__` сначала идут middleware переданные в `__init__`, а уже потом `BASE_MIDDLEWARE`:

```python
self._middleware = (
    middleware.copy()
    if isinstance(middleware, list)
    else [middleware]
    if middleware is not None
    else []
)
self._middleware.extend(
    self.BASE_MIDDLEWARE
    if isinstance(self.BASE_MIDDLEWARE, list)
    else [self.BASE_MIDDLEWARE]
    if self.BASE_MIDDLEWARE is not None
    else []
)
```

То есть если у вас в `__init__` передан `A`, а в `BASE_MIDDLEWARE` лежат `B` и `C`, то итоговый список будет `[A, B, C]`.

Дальше каждый middleware заворачивает предыдущий через `info_decorator`:

```python
for _middleware in self.middleware:
    self.__set_info_middleware(_middleware)
```

Так-как это делается в цикле, последний middleware окажется самым внешним. То есть для `[A, B, C]` порядок вызовов будет `C → B → A → fn`. Это важно помнить, если middleware зависят друг от друга.

---

## `info_decorator` — сердце middleware

```python
def info_decorator(
    self, fn: Callable[P, AsyncGenerator[MiddlewareInfoResult[_R] | None]]
) -> Callable[P, AsyncGenerator[MiddlewareInfoResult[_R] | None]]:
```

Синхронный метод-декоратор, возвращающий асинхронную обёртку. Именно он вызывается в `__set_info_middleware` паука.

Как это работает под капотом:

```python
@wraps(fn)
async def _info_wrapper(
    *args: P.args, **kwargs: P.kwargs
) -> AsyncGenerator[MiddlewareInfoResult[_R] | None]:
    try:
        async for result in fn(*args, **kwargs):
            if not result:
                yield result

            yield await self._process_result(result)

    except Exception as e:
        logger.exception(...)
        await self._handle_error(e)
```

То есть для каждого элемента который отдаёт `fn`, middleware вызывает `_process_result`. Если результат `None` — он всё равно пробрасывается, а потом ещё раз отдаётся `await self._process_result(result)`. Это выглядит странно — см. раздел «Странности» ниже.

---

## Пишем свой Middleware

Например, middleware который логирует каждый добавленный контент:

```python
from .middleware import SpiderMiddleware
from .schema import MiddlewareInfoResult


class LogMiddleware(SpiderMiddleware):
    async def _process_result(
        self, result: MiddlewareInfoResult
    ) -> MiddlewareInfoResult | None:
        logger.info(
            f"[{self.spider.name()}] Добавлен контент: {result.content.title!r}"
        )
        return result

    async def _handle_error(self, exception: Exception) -> None:
        logger.error(f"Ошибка в LogMiddleware: {exception!r}")
```

Или middleware который фильтрует контент без описания:

```python
class DescriptionRequiredMiddleware(SpiderMiddleware):
    async def _process_result(
        self, result: MiddlewareInfoResult
    ) -> MiddlewareInfoResult | None:
        if not result.content.description:
            logger.warning(f"Пропущен {result.content.title!r} — нет описания")
            return None
        return result

    async def _handle_error(self, exception: Exception) -> None:
        pass
```

Всё что вернули из `_process_result` уйдёт дальше по конвейеру. Вернули `None` — дальше ничего не пойдёт.

---

## Что приходит в `result`

`MiddlewareInfoResult` — это наследник `_BaseInfoResult[GetContent, _T]`:

```python
class MiddlewareInfoResult(_BaseInfoResult[GetContent, _T], Generic[_T]):
    model_config = {"arbitrary_types_allowed": True}
    connection: _FastConnection
    pagination: _BasePagination
    start_config: _StartParsingconfig
```

То есть внутри есть:

- **content** — `GetContent` из БД
- **extra_kwargs** — то что паук положил в `create_add(extra_kwargs=...)`
- **connection** — живое подключение к БД
- **pagination** — текущая пагинация, откуда пришёл контент
- **start_config** — стартовая конфигурация парсинга

Про `start_config` подробнее:

```python
class _StartParsingconfig(BaseModel):
    start_page: int
    pagination_kwargs: dict | None
    update: bool
    kwargs: dict = Field(default_factory=dict)
```

Это удобно для логирования и для случаев когда middleware хочет понять контекст парсинга — например, чтобы решить, обновлять или нет.

---

## `pagination` и `is_end`

`_BasePagination` помимо полей имеет вычисляемое свойство:

```python
@computed_field
@property
def is_end(self) -> bool:
    if self.end_page:
        return self.end_page

    if self.total_page:
        return self.current_page >= self.total_page

    return False
```

Логика простая:

1. Если `end_page` явно передан — он в приоритете.
2. Если есть `total_page` — сравниваем `current_page >= total_page`.
3. Иначе — `False`.

Стоит помнить что `end_page=False` не означает «не конец», а просто «не указано вручную». То есть `if self.end_page:` пропустит `False` дальше.

---

## Странности которые стоит знать

### 1. Двойной `_process_result` для `None`

В `_info_wrapper`:

```python
async for result in fn(*args, **kwargs):
    if not result:
        yield result

    yield await self._process_result(result)
```

Если `result` пустой (`None`, `0`, `""`), он сначала отдаётся как есть, а потом ещё раз обрабатывается через `_process_result`. То есть для `None` middleware вызовется дважды, и первый раз результат уйдёт в никуда без обработки. Скорее всего тут имелось в виду `continue`:

```python
if not result:
    yield result
    continue
```

Но пока это не исправлено — имейте в виду.

### 2. `_handle_error` не пробрасывает исключение

После `_handle_error` исключение гасится. То есть упавший middleware не уронит парсинг, но и результат не будет отдан. Это скорее фича, чем баг, но знать надо.

### 3. Обёртка меняет метод у экземпляра

```python
self.start_parsing_generator = wrapper
```

Это подмена метода на уровне инстанса, а не класса. Если создать двух пауков одного класса — у каждого будет своя цепочка middleware. Это скорее ок, но при повторной инициализации того же паука обёртки могут накапливаться.

---

## Что ещё почитать

- `schema.py` — там живут `MiddlewareInfoResult`, `Pagination`, `GetInfoResult` и прочие схемы.
- `spider.py` — метод `__set_info_middleware` показывает как именно middleware встраивается в паука.
- `SPIDER_TOOL.md` — базовые вспомогательные функции паука.
