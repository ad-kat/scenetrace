"""YOLO detection adapter via VSS indexed detection sidecars.

Verified endpoint: GET /api/v1/videos/detections?source=
(Source: retrieval/videos skill — returns YOLO11 bbox JSON already produced at ingest.)
"""
from __future__ import annotations

import logging
from typing import Any

from app.providers.base import Detection, ProviderNotConfigured
from app.providers.vss_client import VssClient

logger = logging.getLogger(__name__)


class YoloDetectionProvider:
    """Reads precomputed YOLO11 detections for a segment source URI."""

    def __init__(self, client: VssClient) -> None:
        self._client = client
        # Populated by agent before detect() when candidate.source_ref is known.
        self._pending_source: str | None = None

    def set_source(self, source: str | None) -> None:
        self._pending_source = source

    async def detect(
        self,
        video_id: str,
        start_sec: float,
        end_sec: float,
        *,
        source: str | None = None,
    ) -> list[Detection]:
        src = source or self._pending_source
        if not src:
            return []
        try:
            data = await self._client.detections(src)
        except Exception as exc:
            # 404 = no sidecar; treat as empty, not fatal.
            logger.info("No detections for source (%s): %s", src[-48:], exc)
            return []

        return _parse_detections(data, start_sec=start_sec, end_sec=end_sec)


def _parse_detections(
    data: dict[str, Any], *, start_sec: float, end_sec: float
) -> list[Detection]:
    out: list[Detection] = []
    frames = data.get("frames") or []
    if not isinstance(frames, list):
        # Fall back to aggregate object_classes when frame list absent.
        for label in data.get("object_classes") or []:
            conf = float(data.get("max_detection_conf") or 0.0)
            out.append(
                Detection(
                    label=str(label),
                    confidence=conf,
                    start_sec=start_sec,
                    end_sec=end_sec,
                )
            )
        return out

    # Sample a few frames inside the window; avoid shipping hundreds of boxes.
    sampled = 0
    for frame in frames:
        if not isinstance(frame, dict):
            continue
        t = float(frame.get("time_sec") or 0.0)
        abs_t = start_sec + t
        if abs_t < start_sec - 0.5 or abs_t > end_sec + 0.5:
            # Frame times are relative to the segment; keep all when relative.
            abs_t = start_sec + t
        for det in frame.get("detections") or []:
            if not isinstance(det, dict):
                continue
            label = det.get("label")
            if not label:
                continue
            conf = float(det.get("confidence") or 0.0)
            bbox = det.get("bbox") or []
            out.append(
                Detection(
                    label=str(label),
                    confidence=conf,
                    start_sec=abs_t,
                    end_sec=abs_t,
                    bbox=[float(x) for x in bbox] if isinstance(bbox, list) else [],
                )
            )
            sampled += 1
            if sampled >= 24:
                return _dedupe_labels(out)
    return _dedupe_labels(out)


def _dedupe_labels(dets: list[Detection]) -> list[Detection]:
    """Keep highest-confidence detection per label for evidence chips."""
    best: dict[str, Detection] = {}
    for d in dets:
        prev = best.get(d.label)
        if prev is None or d.confidence > prev.confidence:
            best[d.label] = d
    return list(best.values())
