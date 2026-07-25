from fastapi import Query


def pagination(
    tag: str | None = Query(
        None, description="Тэг в котором исключительно будет поиск"
    ),
    page: int = Query(1, ge=1, description="Страница для пагинации"),
    limit: int = Query(15, ge=1, le=50, description="Лимит обьектов в ответе"),
):
    return {"tag": tag, "page": page, "limit": limit}
