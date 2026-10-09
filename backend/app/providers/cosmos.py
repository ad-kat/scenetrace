"""NVIDIA Cosmos reasoning adapter — intentionally unconfigured until onboarding.

Do not invent endpoint schemas. Fill in from verified SDK/docs after event onboarding.
Separate embed/retrieval from reasoning — do not assume one universal endpoint.
"""
from __future__ import annotations

from app.providers.base import ProviderNotConfigured, ReasoningResult


class CosmosReasoningProvider:
    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ProviderNotConfigured(
                "NVIDIA_API_KEY must be set with a verified key. "
                "See docs/INTEGRATION_NOTES.md."
            )
        self._api_key = api_key

    async def reason(
        self,
        video_id: str,
        start_sec: float,
        end_sec: float,
        question: str,
        evidence: list[str],
    ) -> ReasoningResult:
        raise ProviderNotConfigured(
            "Cosmos adapter not yet implemented — endpoint and model name unverified."
        )
