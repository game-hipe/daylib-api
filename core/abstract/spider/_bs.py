from typing import Any, Self

from bs4 import BeautifulSoup, ResultSet, Tag

from ...exception import RequiredObjNotFoundException


class _SpiderTag(Tag):
    def select(self, selector, namespaces=None, limit=0, **kwargs) -> ResultSet[Self]:
        return super().select(selector, namespaces, limit, **kwargs)  # type: ignore

    def select_required(
        self, selector: str, namespaces: dict[str, str] | None = None, **kwargs: Any
    ) -> Self:
        if obj := self.select_one(selector, namespaces, **kwargs):
            return obj  # type: ignore

        raise RequiredObjNotFoundException(
            f"Не найден объект с селектором: `{selector}`"
        )


class _SpiderSoup(BeautifulSoup):
    def __init__(
        self,
        markup="",
        features=None,
        builder=None,
        parse_only=None,
        from_encoding=None,
        exclude_encodings=None,
        element_classes=None,
        **kwargs,
    ):
        element_classes = {Tag: _SpiderTag}
        super().__init__(
            markup,
            features,
            builder,
            parse_only,
            from_encoding,
            exclude_encodings,
            element_classes,
            **kwargs,
        )

    def select(
        self, selector, namespaces=None, limit=0, **kwargs
    ) -> ResultSet[_SpiderTag]:
        return super().select(selector, namespaces, limit, **kwargs)  # type: ignore

    def select_required(
        self, selector: str, namespaces: dict[str, str] | None = None, **kwargs: Any
    ) -> _SpiderTag:
        if obj := self.select_one(selector, namespaces, **kwargs):
            return obj  # type: ignore

        raise RequiredObjNotFoundException(
            f"Не найден объект с селектором: `{selector}`"
        )
