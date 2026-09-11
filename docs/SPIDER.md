# Создание паука, его внутреснности и особенности

[По данной ссылке](core/spider/examples/example.py) вы можете увидеть как выглядит самый простой паук
```python
from .share import BaseSpider
from ..manager.client import AiohttpClient


class ExampleSpider(BaseSpider[AiohttpClient, dict]):
    BASE_TAG = "images"
    BASE_URL = "https://example.com"

    async def get_page(self, page, **kwargs):
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

    async def get_info(self, url, **kwargs):
        return self.create_add(
            title="Example",
            url=url,
            poster="https://example.com/poster.jpg",
            extra_kwargs={"example_kwargs": "lol"},
        )
```
Давайте рассмотрим данынй код поближе:
```python
BASE_TAG = "images"
```
Базовый тег который будет присваиваться к каждому обьекту, данная опция необезательная, так-как на одном сайте могут быть 2 или более разных типов данных. Но если его не указать придётся указывать каждый раз в функциях create_add и create_preview.

```python
BASE_URL = "https://example.com"
```
Базовый URL к сайту, данный параметр обязателен если во время инициализации не был указан `abstract = True`.

```python
async def get_page(self, page, **kwargs) -> Pagination: 
    ...
```
Функция для пагинации, главная необходимость получать определённую страницу.
- page - номер страницы к которой нужно обращаться
- kwargs - по большей части для передачи клиенту для запросов

Возращаемый тип данных [Pagination](../core/abstract/spider/schema.py)

```python
async def get_info(self, url, **kwargs) -> GetInfoResult[_R] | AddContent | None:
    ...
```
Функция для получение основных данных, при возвращении None, [Middleware](../core/abstract/spider/middleware.py) будет пропускать мимо себя. При получении GetInfoResult, будет передан дальше по конвейеру при получениее AddContent будет обёрнут в GetInfoResult для единобразие.
- url - страница с данными, для парсинга
- kwargs - по большей части для передачи клиенту для запросов

Разберём мною указанный `abstract`, в начале этого гайда.
```python
class Example(BaseSpider[AiohttpClient, CustomDict], abstract = True):
    BASE_TAG = "images"
    # BASE_URL = "https://example.com"
```
как мы видим мы создали класс Example, но без BASE_URL, и если-бы мы не добавили abstract то случился бы ValueError, так-как BASE_URL не указан. Под капотом всё выглядит так:
```python
def __init_subclass__(cls, abstract=False):
    super().__init_subclass__()
    if abstract:
        return

    if not hasattr(cls, "BASE_URL"):
        URL_ERROR_MESSAGE = f"Не найден URL у паука {cls}"
        logger.error(URL_ERROR_MESSAGE)
        raise ValueError(URL_ERROR_MESSAGE)

    if not cls.BASE_TAG:
        logger.info(
            f"Не был указан обычный тэг для паука {cls},функция `create_content` теперь требует тэг"
        )
```

----------------------
На данный момент мы узнали лишь ввершину айсберга следующий урок будет про внутренности самого BaseSpider, про вспомогательные функции вы можете его найти [здесь](SPIDER_TOOL.md)