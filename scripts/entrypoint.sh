#!/bin/sh
set -e

echo "Applying database migrations..."
alembic upgrade head

exec uv run fastapi run src/main.py
