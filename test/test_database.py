import pytest

from core.entitie import AddContent, ChangeSchema
from core.manager.database import ModelManager, SearchManager


@pytest.mark.asyncio
async def test_add_get_change_delete(model_manager: ModelManager):
    content = AddContent(
        title="Test",
        url="https://example.com/1",
        poster="https://example.com/poster.jpg",
        tag="manga",
        description="Desc",
        fields={"genre": ["Action"]},
    )

    added = await model_manager.add_content(content)

    assert added.id is not None
    assert added.title == "Test"
    assert added.tag.name == "manga"
    assert "genre" in added.fields

    by_id = await model_manager.get_content("id", added.id)
    assert by_id is not None
    assert by_id.title == "Test"

    by_url = await model_manager.get_content("url", "https://example.com/1")
    assert by_url is not None
    assert by_url.id == added.id

    updated = await model_manager.change_content(
        "id",
        added.id,
        ChangeSchema(
            title="Updated",
            description="New",
            fields={"author": ["A"]},
            tag="anime",
        ),
    )

    assert updated.title == "Updated"
    assert updated.tag.name == "anime"
    assert "author" in updated.fields

    assert await model_manager.delete_content("id", added.id) is True
    assert await model_manager.get_content("id", added.id) is None


@pytest.mark.asyncio
async def test_random_content_and_connection(model_manager: ModelManager):
    await model_manager.add_content(
        AddContent(
            title="A",
            url="https://example.com/a",
            poster="https://example.com/a.jpg",
            tag="test",
        )
    )

    random_content = await model_manager.random_content()
    assert random_content is not None

    async with model_manager.connect() as connection:
        assert await connection.in_database("https://example.com/a") is True


@pytest.mark.asyncio
async def test_search(
    model_manager: ModelManager,
    search_manager: SearchManager,
):
    await model_manager.add_content(
        AddContent(
            title="Naruto",
            url="https://example.com/naruto",
            poster="https://example.com/naruto.jpg",
            tag="anime",
            description="Ninja",
            fields={"genre": ["Action"]},
        )
    )
    await model_manager.add_content(
        AddContent(
            title="Bleach",
            url="https://example.com/bleach",
            poster="https://example.com/bleach.jpg",
            tag="anime",
            description="Soul",
            fields={"genre": ["Action"]},
        )
    )

    by_title = await search_manager.search_by_title("Naru")
    assert by_title.total_items == 1
    assert by_title.items[0].title == "Naruto"

    by_fields = await search_manager.search_by_fields({"genre": ["Action"]})
    assert by_fields.total_items == 2

    by_tag = await search_manager.search(tag="anime")
    assert by_tag.total_items == 2
