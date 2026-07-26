import importlib

from loguru import logger

from ...abstract.client import BaseClient
from ...abstract.spider import BaseSpider

ERROR_SPIDER_NOT_FOUND = "Паук {spider} не найден. Пожалуйста, проверьте наличие файла __all__ в модуле spider."
ERROR_ALL_NOT_FOUND = "Не удалось загрузить список доступных парсеров. Пожалуйста, проверьте наличие файла __all__ в модуле spider."
WARNING_SPIDER_BANNED = "Парсер {spider} указан как заблокированный. Парсер будет пропущен при инициализации"


def load_spider(
    clients: list[BaseClient] | BaseClient,
    banned_spider: list[type[BaseSpider] | BaseSpider] | None = None,
    general_kwargs: dict | None = None,
    extra_kwargs: dict[type[BaseSpider] | str, dict] | None = None,
) -> list[BaseSpider]:
    """Загрузка всех пауков из директории :dir:`spider`
    Загружает всех пауков из директории `spider`, но только те которые могут работать в зависимости от передоваемых клиентов.
    Если паук нуждается в клиенте который не передан, он будет пропущен.

    Args:
        clients (list[BaseClient] | BaseClient): Клиенты для запросов
        banned_spider (list[type[BaseSpider]  |  BaseSpider] | None, optional): Забаненные пауки. По умолчанию None.
        general_kwargs (dict | None, optional): Общие ключевые параметры для всех пауков. По умолчанию None.
        extra_kwargs (dict[type[BaseSpider], dict] | None, optional): Ключевые параметры для отдельных пауков. По умолчанию None.

    Raises:
        ImportError: Если не удалось загрузить список доступных пауков

    Returns:
        list[BaseSpider]: Список загруженных пауков
    """
    clients = clients if isinstance(clients, list) else [clients]
    banned_spider: list[type[BaseSpider]] = (
        [
            spider if isinstance(spider, type) else type(spider)
            for spider in banned_spider
        ]
        if banned_spider
        else []
    )

    spiders: list[BaseSpider] = []
    spider_module = importlib.import_module("...spider", package=__package__)

    if not hasattr(spider_module, "__all__"):
        logger.error(ERROR_ALL_NOT_FOUND)
        raise ImportError(ERROR_ALL_NOT_FOUND)

    for spider_name in spider_module.__all__:
        if not hasattr(spider_module, spider_name):
            logger.error(ERROR_SPIDER_NOT_FOUND.format(spider=spider_name))
            continue

        spider_factory: type[BaseSpider] = getattr(spider_module, spider_name)
        if spider_factory in banned_spider:
            logger.warning(WARNING_SPIDER_BANNED.format(spider=spider_name))
            continue

        try:
            client_type = spider_factory.need_client()
        except TypeError:
            logger.warning(f"Не указан необходимый клиент у паука: `{spider_factory}`")
            continue

        for client in clients:
            if isinstance(client, client_type):
                kwargs = (
                    extra_kwargs.get(
                        spider_factory, extra_kwargs.get(spider_factory.name(), {})
                    )
                    if extra_kwargs
                    else {}
                )

                if general_kwargs:
                    kwargs |= general_kwargs

                spider = spider_factory(client, **kwargs)
                spiders.append(spider)
                break

        else:
            logger.warning(
                f"Не найден клиент для `{spider_factory}`, необходимый тип: `{client_type}`"
            )

    return spiders
