from typing import TYPE_CHECKING, TypeAlias

if TYPE_CHECKING:
    from ...abstract.spider import BaseSpider

__all__ = ["SPIDER"]

SPIDER: TypeAlias = "str | BaseSpider | type[BaseSpider]"
"""Типы которые могут отдать название"""
