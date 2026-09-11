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
    database_path: str = ":memory:"
    max_model_calls: int = Field(default=6, ge=1, le=6)
    max_investigation_rounds: int = Field(default=3, ge=1, le=20)
    max_file_bytes: int = Field(default=1_000_000, ge=1, le=100_000_000)
    max_index_bytes: int = Field(default=25_000_000, ge=1, le=2_000_000_000)
    max_index_files: int = Field(default=10_000, ge=1, le=1_000_000)
    retrieval_top_k: int = Field(default=8, ge=1, le=100)
    guard_timeout_seconds: float = Field(default=5, gt=0, le=30)
    guard_output_limit: int = Field(default=16_384, ge=1_024, le=65_536)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance."""

    return Settings()
