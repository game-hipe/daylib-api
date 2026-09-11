# Вспомогательные функции паука и его инструментарий

[По данной ссылке](../core/spider/examples/example.py) вы можете увидеть как выглядит самый простой паук, но помимо `get_page` и `get_info` у `BaseSpider` есть ещё куча вспомогательных функций которые облегчают жизнь разработчику. О них и поговорим.

## `create_preview`

```python
def create_preview(
    self, title: str, url: str, poster: str, tag: str | None = None
) -> PreviewContent:
```

Создать схему для пагинации. Используется внутри `get_page` что-бы не собирать `PreviewContent` руками.

- **title** — Название
- **url** — URL
- **poster** — URL к постеру
- **tag** — Тэг контента пример: `manga`, `anime`. По умолчанию `None`.

```python
raise ValueError("Параметр 'tag' обязателен, если BASE_TAG не задан!")
```

Если `BASE_TAG` не задан и `tag` не передан — будет `ValueError`. Так-что либо указываем `BASE_TAG` у паука, либо каждый раз передаём `tag`.

Внутри делает `self.urljoin(url)` и `self.urljoin(poster)`, так-что можно спокойно кидать относительные пути:

```python
self.create_preview(
    title="Example",
    url="/example/1",
    poster="/poster/1.jpg",
)
```

---

## `create_add`

```python
def create_add(
    self,
    title: str,
    url: str,
    poster: str,
    tag: str | None = None,
    description: str | None = None,
    other: Any | None = None,
    fields: dict[str, list[str]] | None = None,
    extra_kwargs: _R | None = None,
) -> GetInfoResult[_R]:
```

Создать полноценную схему для добавления данных в БД. Возвращает уже обёрнутый в `GetInfoResult`, так-что не придётся это делать руками.

- **title** — Название
- **url** — URL
- **poster** — URL к постеру
- **tag** — Тэг контента. По умолчанию `None`.
- **description** — Описание контента. По умолчанию `None`.
- **other** — Остальные параметры. По умолчанию `None`.
- **fields** — Заполнения, которые важны при поиске. По умолчанию `None`.
- **extra_kwargs** — Дополнительные данные, которые могут понадобиться в будущем. По умолчанию `None`.

Тут тоже работает проверка на `tag` и `urljoin`.

```python
return self.create_add(
    title="Example",
    url=url,
    poster="https://example.com/poster.jpg",
    extra_kwargs={"example_kwargs": "lol"},
)
```

---

## `create_pagination`

```python
def create_pagination(
    self,
    current_page: int,
    items: list[PreviewContent],
    total_page: int | None = None,
    end_page: bool | None = None,
) -> Pagination:
```

Создать схему пагинации. Используется внутри `get_page`.

- **current_page** — Текущая страница
- **items** — Элементы для пагинации
- **total_page** — Общее количество страниц, нужно для пагинации пачками. По умолчанию `None`.
- **end_page** — Указать конец ли это страницы вручную, имеет приоритет у функции `Pagination`. По умолчанию `None`.

```python
return self.create_pagination(
    current_page=page,
    items=[
        self.create_preview(
            title="Example",
            url="https://example.com",
            poster="https://example.com/poster.jpg",
        )
    ],
    end_page=True,
)
```

---

## `urljoin`

```python
def urljoin(self, url: str) -> str:
    """Соеденить относительный URL с базовым"""
    return urljoin(self.BASE_URL, url)
```

Склеивает относительный URL с `BASE_URL`. Работает через `urllib.parse.urljoin`, так-что если передать уже абсолютный URL — он и останется абсолютным.

```python
self.urljoin("/example/1")  # https://example.com/example/1
self.urljoin("https://other.com/1")  # https://other.com/1
```

---

## `fields_validate`

```python
def fields_validate(
    self, fields: dict[str, list[str]], custom_map: dict[str, str] | None = None
) -> dict[str, list[str]]:
```

Валидация заполнений. Приводит ключи к единому виду через `FIELDS_MAP` или `custom_map`.

- **fields** — Заполнение
- **custom_map** — Карта для заполнений, меняет названия ключей. По умолчанию `None`.

```python
FIELDS_MAP: dict[str, str] | None = None
"""Карта для заполнений пример: `{'Теги': 'genre'}`"""
```

Если карта не указана — будет варнинг, но функция всё равно отработает. Все ключи и значения тримятся.

```python
self.fields_validate({"Теги": ["Экшен", "Фэнтези"]})
# {"genre": ["Экшен", "Фэнтези"]}
```

---

## `create_soup`

```python
def create_soup(
    self, markup: _IncomingMarkup, features: str | None = None
) -> _SpiderSoup:
```

Создать Soup для парсинга. Возвращает кастомный `_SpiderSoup`, подробнее в его доке.

- **markup** — Данные для парсинга
- **features** — Движок для парсинга. По умолчанию `None`.

Если `features` не передан — берётся `self.features`, который в свою очередь равен `BASE_FEATURES` или тому что передали в `__init__`.

```python
soup = self.create_soup(html)
titles = soup.find_all("h2")
```

---

## `need_client`

```python
@classmethod
def need_client(cls) -> type[_C]:
```

Возвращает тип клиента для запросов. Нужен для автоматической инициализации.

Если `REQUEST_CLIENT` не задан — пытается достать тип из `__orig_bases__`. Если там `TypeVar` — кидает `TypeError`.

Обычно вызывать руками не надо, оно само подставится в `__init_subclass__`:

```python
def __init_subclass__(cls, abstract=False):
    super().__init_subclass__(abstract)
    try:
        if cls.REQUEST_CLIENT is None:
            cls.REQUEST_CLIENT = cls.need_client()
    except TypeError:
        pass
```

---

## `name`

```python
@classmethod
def name(cls) -> str:
    return cls.__name__
```

Возвращает имя класса. Используется в логах и алертах:

```python
await self._alert(f"Паук `{self.name()}`, начал свою работу.", "info")
```

---

## `change_middleware`

```python
def change_middleware(self) -> bool:
```

Меняет `use_middleware` на противоположный. Возвращает текущее значение.

```python
spider.change_middleware()  # False
spider.change_middleware()  # True
```

---

## Свойства

### `client`

```python
@property
def client(self) -> _C:
```

Клиент для запросов. Именно тот что передали в `__init__`.

### `kwargs`

```python
@property
def kwargs(self) -> Any:
```

Кварги переданные в паука во время инициализации. Возвращает копию, так-что можно спокойно менять.

---

## Что ещё важно знать

### `BASE_FEATURES`

```python
BASE_FEATURES: str = "html.parser"
```

Базовый движок для парсинга. Можно переопределить у паука или передать в `__init__`.

### `BASE_BATCH`

```python
BASE_BATCH: int = 10
```

Базовое количество одновременных запросов. Используется в `pagination` при `batched`.

### `BASE_MIDDLEWARE`

```python
BASE_MIDDLEWARE: list[type[SpiderMiddleware]] | type[SpiderMiddleware] | None = None
```

Базовые Middleware. Можно указать как один класс, так и список.

### `REQUEST_CLIENT`

```python
REQUEST_CLIENT: type[BaseClient] | None = None
```

Клиент для запросов для ручного выставления. Если не указан — берётся из generic-параметра.

---

## Полезные мелочи

- `create_preview`, `create_add`, `create_pagination` — это фабрики, не надо собирать схемы руками.
- `urljoin` работает и с абсолютными URL, так-что можно не париться.
- `fields_validate` приводит ключи к единому виду, что важно при поиске.
- `create_soup` уже знает про `features`, не надо передавать его каждый раз.

На этом всё, следующий урок будет про [Middleware](MIDDLEWARE.md) и как их готовить.