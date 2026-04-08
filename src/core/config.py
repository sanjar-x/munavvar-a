from functools import lru_cache
from typing import Annotated, Any, Literal, Self

from pydantic import BeforeValidator, computed_field, model_validator
from pydantic.types import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


def parse_cors(v: Any) -> list[str] | str:
    """Парсит CORS из .env ('http://localhost,https://prod.com') в []."""
    if isinstance(v, str) and not v.startswith("["):
        return [i.strip() for i in v.split(",") if i.strip()]
    if isinstance(v, list):
        return v
    raise ValueError(v)


class Settings(BaseSettings):
    PROJECT_NAME: str = "Enterprise API"
    VERSION: str = "1.0.0"
    ENVIRONMENT: Literal["dev", "test", "prod"] = "dev"
    DEBUG: bool = False

    API_V1_STR: str = "/api/v1"
    API_V2_STR: str = "/api/v2"
    ALGORITHM: str = "HS256"

    SECRET_KEY: SecretStr
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    @model_validator(mode="after")
    def validate_secret_key(self) -> Self:
        key = self.SECRET_KEY.get_secret_value()
        if len(key) < 32:
            raise ValueError("SECRET_KEY должен содержать минимум 32 символа")
        return self

    CORS_ORIGINS: Annotated[list[str] | str, BeforeValidator(parse_cors)] = []

    ADMIN_PHONE: str | None = None
    ADMIN_PASSWORD: SecretStr | None = None

    PGHOST: str
    PGPORT: int
    PGUSER: str
    PGPASSWORD: SecretStr
    PGDATABASE: str

    @computed_field
    @property
    def database_url(self) -> str | URL:
        password: str = self.PGPASSWORD.get_secret_value()
        return (
            f"postgresql+asyncpg://{self.PGUSER}:{password}"
            f"@{self.PGHOST}:{self.PGPORT}/{self.PGDATABASE}"
        )

    REDISHOST: str = "localhost"
    REDISPORT: int = 6379
    REDISUSER: str = ""
    REDISPASSWORD: SecretStr = SecretStr("")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # ty:ignore[missing-argument]


# Глобальный объект настроек, который мы будем импортировать во всем проекте
settings: Settings = get_settings()
