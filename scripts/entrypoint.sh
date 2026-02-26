#!/bin/sh
set -e

echo "Applying database migrations..."
alembic upgrade head

exec fastapi run src/main.py
