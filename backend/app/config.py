"""Application configuration loaded from environment / .env."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    scenetrace_mode: str = "mock"
    scenetrace_media_dir: Path = Path("./media")
    scenetrace_cors_origins: str = "http://localhost:5173"

    # Sponsor keys — intentionally optional; kept empty until verified.
    vast_api_url: str = ""
    vast_api_key: str = ""
    nvidia_api_key: str = ""
    wandb_api_key: str = ""
    wandb_model: str = ""

    search_timeout_seconds: float = 15.0
    reasoning_timeout_seconds: float = 25.0

    @field_validator("scenetrace_mode")
    @classmethod
    def _valid_mode(cls, v: str) -> str:
        allowed = {"mock", "live", "hybrid"}
        if v not in allowed:
            raise ValueError(f"scenetrace_mode must be one of {allowed}")
        return v

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.scenetrace_cors_origins.split(",") if o.strip()]

    @property
    def is_mock(self) -> bool:
        return self.scenetrace_mode == "mock"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
