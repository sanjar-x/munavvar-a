#!/bin/sh
set -e

echo "Applying database migrations..."
uv run alembic upgrade head

exec uv run fastapi run src/main.py
