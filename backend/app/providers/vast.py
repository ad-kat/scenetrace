"""VAST / VSS hybrid search adapter.

Uses verified retrieval APIs only:
  POST /api/v1/search
  GET  /api/v1/tools/segments  (temporal expand)
  POST /api/v1/agent/search-and-answer  (optional grounded answer cache)

Source: vast-builders-challenge/.cursor/skills/retrieval/{search,agent-qa,videos}
"""
from __future__ import annotations

import logging
from typing import Any

from app.providers.base import Candidate
from app.providers.vss_client import VssClient

logger = logging.getLogger(__name__)


def _as_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _row_to_candidate(row: dict[str, Any]) -> Candidate | None:
    start = _as_float(row.get("segment_start_sec"), row.get("best_match_start_sec"))
    end = _as_float(row.get("segment_end_sec"), row.get("best_match_end_sec"))
    if start is None or end is None or end <= start:
        return None
    score = _as_float(row.get("similarity_score"))
    source = row.get("source") or row.get("preview_source")
    caption = row.get("reasoning_content")
    if isinstance(caption, str):
        caption = caption.strip() or None
    else:
        caption = None
    return Candidate(
        start_sec=start,
        end_sec=end,
        score=score,
        source_ref=source if isinstance(source, str) else None,
        caption=caption,
        original_video=row.get("original_video")
        if isinstance(row.get("original_video"), str)
        else None,
        object_classes=_normalize_classes(row.get("object_classes")),
        extra={
            "filename": row.get("filename"),
            "location": row.get("location"),
            "camera_id": row.get("camera_id"),
            "detection_count": row.get("detection_count"),
        },
    )


def _normalize_classes(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw if x]
    if isinstance(raw, str):
        # Search rows may return a single class string or comma-separated.
        parts = [p.strip() for p in raw.replace(";", ",").split(",")]
        return [p for p in parts if p]
    return [str(raw)]


class VastSearchProvider:
    """Live VSS search over the team's indexed archive."""

    def __init__(self, client: VssClient) -> None:
        self._client = client
        self.last_answer: str | None = None
        self.last_synthesis: str | None = None

    async def search(
        self,
        video_id: str,
        query: str,
        top_k: int = 5,
        *,
        original_video: str | None = None,
        object_classes: list[str] | None = None,
        metadata_filters: dict[str, Any] | None = None,
        min_similarity: float = 0.3,
    ) -> list[Candidate]:
        if not query.strip():
            return []

        filters: dict[str, Any] = dict(metadata_filters or {})
        if object_classes:
            # Schema field is object_classes; API accepts a single class string.
            filters["object_classes"] = object_classes[0]

        body: dict[str, Any] = {
            "query": query,
            "top_k": max(top_k * 3, top_k),
            "llm_top_n": min(3, max(1, top_k)),
            "min_similarity": min_similarity,
            "include_public": True,
        }
        if filters:
            body["metadata_filters"] = filters

        try:
            data = await self._client.search(body)
        except Exception as exc:
            logger.error("VSS search failed: %s", exc)
            raise

        synth = data.get("llm_synthesis") or {}
        if isinstance(synth, dict):
            self.last_synthesis = synth.get("response")
        else:
            self.last_synthesis = None

        rows = list(data.get("results") or [])
        candidates: list[Candidate] = []
        for row in rows:
            if original_video and row.get("original_video") != original_video:
                continue
            cand = _row_to_candidate(row)
            if cand:
                candidates.append(cand)
            if len(candidates) >= top_k:
                break

        # Video-scoped fallback: use segment inventory when global search misses.
        if original_video and not candidates:
            candidates = await self._candidates_from_segments(
                original_video, query, top_k=top_k
            )

        return candidates[:top_k]

    async def expand(
        self,
        video_id: str,
        start_sec: float,
        end_sec: float,
        query: str,
        *,
        original_video: str | None = None,
        window_sec: float = 15.0,
    ) -> list[Candidate]:
        window_start = max(0.0, start_sec - window_sec)
        window_end = end_sec + window_sec
        if not original_video:
            return [
                Candidate(
                    start_sec=window_start,
                    end_sec=max(window_start + 1.0, window_end),
                    score=None,
                    source_ref=None,
                    caption=(
                        f"Temporal window {window_start:.1f}–{window_end:.1f}s "
                        "(no original_video bound to this session event)."
                    ),
                )
            ]

        segs = await self._client.segments(original_video)
        rows = list(segs.get("segments") or [])
        matched: list[Candidate] = []
        for row in rows:
            cand = _row_to_candidate(row)
            if not cand:
                continue
            # Keep segments overlapping the follow-up window.
            if cand.end_sec < window_start or cand.start_sec > window_end:
                continue
            if query.strip() and cand.caption:
                # Soft preference: keep all overlapping; caption used as evidence.
                pass
            matched.append(cand)

        if not matched:
            # Still return the bounded window so the UI has a seekable moment.
            matched.append(
                Candidate(
                    start_sec=window_start,
                    end_sec=max(window_start + 1.0, min(window_end, end_sec + window_sec)),
                    score=None,
                    source_ref=None,
                    caption=(
                        f"Temporal window {window_start:.1f}–{window_end:.1f}s "
                        f"around prior evidence (no overlapping indexed segments)."
                    ),
                    original_video=original_video,
                )
            )
        return matched[:5]

    async def grounded_answer(
        self,
        query: str,
        *,
        original_video: str | None = None,
        object_classes: list[str] | None = None,
        top_k: int = 5,
    ) -> str | None:
        try:
            if original_video:
                data = await self._client.agent_ask(
                    {
                        "question": query,
                        "original_video": original_video,
                        "top_k": top_k,
                    }
                )
            else:
                body: dict[str, Any] = {
                    "query": query,
                    "top_k": top_k,
                    "llm_top_n": min(3, top_k),
                    "min_similarity": 0.3,
                    "include_public": True,
                }
                if object_classes:
                    body["metadata_filters"] = {"object_classes": object_classes[0]}
                data = await self._client.search_and_answer(body)
            answer = data.get("answer")
            if isinstance(answer, str) and answer.strip():
                self.last_answer = answer.strip()
                return self.last_answer
        except Exception as exc:
            logger.warning("Grounded answer failed: %s", exc)
        return self.last_synthesis

    async def _candidates_from_segments(
        self, original_video: str, query: str, top_k: int
    ) -> list[Candidate]:
        segs = await self._client.segments(original_video)
        rows = list(segs.get("segments") or [])
        q_terms = {t for t in query.lower().split() if len(t) > 2}
        scored: list[tuple[int, Candidate]] = []
        for row in rows:
            cand = _row_to_candidate(row)
            if not cand:
                continue
            text = (cand.caption or "").lower()
            overlap = sum(1 for t in q_terms if t in text) if q_terms else 0
            scored.append((overlap, cand))
        scored.sort(key=lambda x: x[0], reverse=True)
        # Prefer term overlap; otherwise return earliest segments.
        if scored and scored[0][0] > 0:
            return [c for _, c in scored[:top_k]]
        return [c for _, c in scored[:top_k]]
