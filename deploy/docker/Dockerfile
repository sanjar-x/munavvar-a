# ==========================================
# СТАДИЯ 1: Сборка (Builder)
# Используем полную версию для компиляции пакетов
# ==========================================
FROM ghcr.io/astral-sh/uv:python3.14-trixie AS builder

ENV UV_COMPILE_BYTECODE=1 
ENV UV_LINK_MODE=copy
ENV UV_NO_DEV=1
ENV UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Кэшируем и устанавливаем только зависимости
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

# Копируем код и "доустанавливаем" проект
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable


# ==========================================
# СТАДИЯ 2: Финальный образ (Production)
# ИСПОЛЬЗУЕМ SLIM ВЕРСИЮ! Образ похудеет в 6-7 раз.
# ==========================================
FROM python:3.14-slim-trixie

# Создаем пользователя без прав root
RUN groupadd --system --gid 999 nonroot \
    && useradd --system --gid 999 --uid 999 --create-home nonroot

WORKDIR /app

# Копируем готовое окружение и код из билдера, сразу меняя владельца
COPY --from=builder --chown=nonroot:nonroot /app /app

# Активируем виртуальное окружение
ENV PATH="/app/.venv/bin:$PATH"

RUN chmod +x /app/scripts/entrypoint.sh

# Переключаемся на безопасного пользователя
USER nonroot

# Запускаем FastAPI напрямую. 
# CMD ["fastapi", "run", "src/main.py", "--host", "0.0.0.0", "--port", "8000"]
# (PaaS-ready) вариант:
CMD ["/app/scripts/entrypoint.sh"]