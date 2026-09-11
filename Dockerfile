FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_PROGRESS=1 \
    PLAYWRIGHT_BROWSERS_PATH=/app/.playwright-browsers

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY . .

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Устанавливаем Chromium и ВСЕ его системные зависимости через patchright
RUN uv run patchright install-deps chromium && \
    uv run patchright install chromium

FROM python:3.14.6-slim-bookworm

WORKDIR /app

# Устанавливаем только минимальный набор, который может понадобиться для отладки
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libatspi2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Копируем виртуальное окружение и установленные браузеры
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/.playwright-browsers /app/.playwright-browsers

COPY --from=builder /app /app

# Устанавливаем переменные окружения
ENV PATH="/app/.venv/bin:$PATH" \
    PLAYWRIGHT_BROWSERS_PATH=/app/.playwright-browsers

COPY entrypoint.sh .
RUN chmod +x ./entrypoint.sh

ENTRYPOINT [ "./entrypoint.sh" ]