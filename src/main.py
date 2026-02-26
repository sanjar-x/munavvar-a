from fastapi.applications import FastAPI

from src.api.server import create_app

app: FastAPI = create_app()
