from fastapi.applications import FastAPI

import src.infrastructure.database.models  # noqa: F401
from src.api.server import create_app

app: FastAPI = create_app()
