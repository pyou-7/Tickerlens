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
    # Shared passcode gate for the publicly hosted site (Railway). When set,
    # every route except /login, /logout, /healthz and /static/* requires the
    # passcode (see tickerlens.auth). When unset (local dev) the gate is
    # inactive and the site stays open.
    tickerlens_passcode: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
