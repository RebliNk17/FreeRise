from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    test_database_url: str = "postgresql+psycopg://freerise:freerise@localhost:5432/freerise_test"
    credentials_key: str
    session_secret: str
    env: str = Field("development", validation_alias="FREERISE_ENV")
    # Login TOTP; can be switched off locally only — production always requires it.
    login_totp: bool = Field(True, validation_alias="FREERISE_LOGIN_TOTP")
    tz: str = "Asia/Jerusalem"


@lru_cache
def get_settings() -> Settings:
    return Settings()
