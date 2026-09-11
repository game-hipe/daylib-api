from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...abstract.spider import BaseSpider

__all__ = ["SPIDER"]

type SPIDER = "str | BaseSpider | type[BaseSpider]"
"""Типы которые могут отдать название"""
