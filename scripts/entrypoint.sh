#!/bin/sh
set -e



echo "Applying database migrations..."
uv run alembic upgrade head || { echo "Migration failed, aborting startup"; exit 1; }

exec uv run fastapi run src/main.py
