#!/bin/sh
set -e

echo "Bootstrapping Alembic state..."
uv run python scripts/bootstrap_alembic.py

echo "Applying database migrations..."
uv run alembic upgrade head

exec uv run fastapi run src/main.py
