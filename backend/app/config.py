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

    # Application-owned VSS credentials (deploy Secret uses these names).
    vss_url: str = ""
    vss_username: str = ""
    vss_password: str = ""

    # Legacy placeholders from TRD — not used for VSS JWT auth.
    vast_api_url: str = ""
    vast_api_key: str = ""
    nvidia_api_key: str = ""
    wandb_api_key: str = ""
    wandb_model: str = ""

    search_timeout_seconds: float = 30.0
    reasoning_timeout_seconds: float = 45.0
    explore_limit: int = 48

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

    @property
    def resolved_vss_url(self) -> str:
        return self.vss_url or os.environ.get("INGRESS_URL", "") or self.vast_api_url

    @property
    def resolved_vss_username(self) -> str:
        return self.vss_username or os.environ.get("USERNAME", "")

    @property
    def resolved_vss_password(self) -> str:
        return self.vss_password or os.environ.get("PASSWORD", "")

    @property
    def vss_configured(self) -> bool:
        return bool(
            self.resolved_vss_url
            and self.resolved_vss_username
            and self.resolved_vss_password
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
