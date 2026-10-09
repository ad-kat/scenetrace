"""VAST AI OS search adapter — intentionally unconfigured until onboarding.

Fill in verified endpoint and schema from docs/INTEGRATION_NOTES.md once
the event SDK is confirmed. Do not invent request/response shapes.
"""
from __future__ import annotations

from app.providers.base import Candidate, ProviderNotConfigured


class VastSearchProvider:
    """Raises ProviderNotConfigured until a verified endpoint is wired in."""

    def __init__(self, api_url: str, api_key: str) -> None:
        if not api_url or not api_key:
            raise ProviderNotConfigured(
                "VAST_API_URL and VAST_API_KEY must be set with verified credentials. "
                "See docs/INTEGRATION_NOTES.md."
            )
        self._api_url = api_url
        self._api_key = api_key

    async def search(self, video_id: str, query: str, top_k: int = 5) -> list[Candidate]:
        raise ProviderNotConfigured("VAST adapter not yet implemented — endpoint schema unverified.")

    async def expand(
        self, video_id: str, start_sec: float, end_sec: float, query: str
    ) -> list[Candidate]:
        raise ProviderNotConfigured("VAST adapter not yet implemented — endpoint schema unverified.")
