Современный высокопроизводительный бэкенд на базе FastAPI и PostgreSQL, построенный по принципам Clean Architecture (Чистой архитектуры) и Modular Monolith.

🚀 Технологический стек
Runtime: Python 3.14.3
Package Manager: uv
Web Framework: FastAPI
Database: PostgreSQL 16
ORM: SQLAlchemy 2.0 (Async Mode)
Migrations: Alembic
Validation: Pydantic V2
Logging: Structlog

🏗 Архитектурные паттерны
Проект следует принципам DDD (Domain-Driven Design) и разделен на логические слои:
API Layer (src/api): Маршрутизация, зависимости и обработка HTTP-ошибок.
Core Layer (src/core): Глобальные настройки, безопасность и базовые исключения.
Infrastructure Layer (src/infrastructure): Реализация работы с БД (сессии, модели) и внешними клиентами.
Module Layer (src/modules): Вертикальные срезы бизнес-логики (Users, Orders и т.д.). Каждый модуль содержит свои модели, сервисы и роутеры.
Common Layer (src/common): Общие интерфейсы паттернов Repository и Unit of Work (UoW).


uv run fastapi dev src/main.py