import pytest
from pydantic import ValidationError

from core.abstract.spider.schema import _BasePagination
from core.entitie.schema import (
    AddContent,
    ChangeSchema,
    DataField,
    GetContent,
    PaginationSchema,
)


def test_base_pagination_is_end():
    assert _BasePagination(current_page=1, total_page=2).is_end is False
    assert _BasePagination(current_page=2, total_page=2).is_end is True
    assert _BasePagination(current_page=1, end_page=True).is_end is True
    assert _BasePagination(current_page=1, total_page=2, end_page=False).is_end is False


def test_add_content_schema():
    content = AddContent(
        title="Test",
        url="https://example.com/1",
        poster="https://example.com/poster.jpg",
        tag="manga",
        description="Desc",
        fields={"genre": ["Action"]},
    )

    assert content.title == "Test"
    assert str(content.url) == "https://example.com/1"
    assert content.fields == {"genre": ["Action"]}


def test_get_content_schema():
    content = GetContent(
        id=1,
        title="Test",
        url="https://example.com/1",
        poster="https://example.com/poster.jpg",
        tag=DataField(id=1, name="manga"),
    )

    assert content.id == 1
    assert content.tag.name == "manga"


def test_change_schema():
    change = ChangeSchema(title="New", tag="anime", fields={"author": ["A"]})
    assert change.title == "New"
    assert change.tag == "anime"
    assert change.fields == {"author": ["A"]}


def test_pagination_schema():
    item = GetContent(
        id=1,
        title="Test",
        url="https://example.com/1",
        poster="https://example.com/poster.jpg",
        tag=DataField(id=1, name="manga"),
    )
    pagination = PaginationSchema(
        current_page=1,
        total_page=1,
        total_items=1,
        items=[item],
    )

    assert pagination.total_items == 1
    assert pagination.items[0].title == "Test"


def test_invalid_url():
    with pytest.raises(ValidationError):
        AddContent(
            title="Test",
            url="not-url",
            poster="https://example.com/poster.jpg",
            tag="manga",
        )