from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment and .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    edgar_user_agent: str = Field(min_length=1)
    edgar_cache_dir: Path = Path(".edgar_cache")
    database_url: str = "sqlite:///tickerlens.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()
