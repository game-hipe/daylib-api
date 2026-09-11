from fastapi import Query


def pagination(
    tag: str | None = Query(
        default=None, description="Тэг в котором исключительно будет поиск"
    ),
    page: int = Query(default=1, ge=1, description="Страница для пагинации"),
    limit: int = Query(default=15, ge=1, le=50, description="Лимит обьектов в ответе"),
):
    return {"tag": tag, "page": page, "limit": limit}
