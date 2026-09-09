"""Typed application configuration."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or ``.env``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="REMEDYGRAPH_",
        extra="ignore",
    )

    app_name: str = "RemedyGraph API"
    app_version: str = "0.1.0"
    environment: str = "development"
    workspace_root: Path = Field(default_factory=Path.cwd)
    llm_provider: Literal["mock"] = "mock"
    frontend_origin: str = "http://localhost:5173"
    max_model_calls: int = Field(default=6, ge=1, le=100)
    max_investigation_rounds: int = Field(default=3, ge=1, le=20)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance."""

    return Settings()
