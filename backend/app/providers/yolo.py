"""YOLO detection adapter — intentionally unconfigured until onboarding."""
from __future__ import annotations

from app.providers.base import Detection, ProviderNotConfigured


class YoloDetectionProvider:
    def __init__(self, endpoint: str) -> None:
        if not endpoint:
            raise ProviderNotConfigured(
                "YOLO endpoint not configured. See docs/INTEGRATION_NOTES.md."
            )
        self._endpoint = endpoint

    async def detect(self, video_id: str, start_sec: float, end_sec: float) -> list[Detection]:
        raise ProviderNotConfigured("YOLO adapter not yet implemented — endpoint schema unverified.")
