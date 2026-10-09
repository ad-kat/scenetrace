"""Deterministic orchestration state machine for investigation requests.

Step order:
1. Validate query, video_id, session, selected_event.
2. Resolve follow-up window via session-scoped event ID (never cross-session).
3. Call SearchProvider.search or SearchProvider.expand.
4. Normalize candidates; reject out-of-range; deduplicate overlapping windows.
5. Optionally run DetectionProvider on up to 3 candidates.
6. Optionally run ReasoningProvider on candidate windows.
7. Build evidence-backed InvestigateResponse.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field

from app.providers.base import (
    Candidate,
    DetectionProvider,
    ReasoningProvider,
    SearchProvider,
)
from app.schemas import (
    ErrorDetail,
    EvidenceItem,
    Event,
    InvestigateRequest,
    InvestigateResponse,
    ProviderMode,
    ToolTraceEntry,
    VerificationStatus,
)

logger = logging.getLogger(__name__)

_FOLLOW_UP_WINDOW_SEC = 15.0


@dataclass
class SessionStore:
    """In-memory session store. Not durable across restarts."""
    _sessions: dict[str, dict[str, Event]] = field(default_factory=dict)

    def get_or_create(self, session_id: str | None) -> str:
        if not session_id or session_id not in self._sessions:
            sid = str(uuid.uuid4())
            self._sessions[sid] = {}
            return sid
        return session_id

    def store_events(self, session_id: str, events: list[Event]) -> None:
        self._sessions.setdefault(session_id, {})
        for evt in events:
            self._sessions[session_id][evt.event_id] = evt

    def get_event(self, session_id: str, event_id: str) -> Event | None:
        return self._sessions.get(session_id, {}).get(event_id)


_session_store = SessionStore()


def _dedup_candidates(candidates: list[Candidate]) -> list[Candidate]:
    """Remove heavily overlapping candidates (>50 % overlap)."""
    kept: list[Candidate] = []
    for c in candidates:
        overlap = False
        for k in kept:
            lo = max(c.start_sec, k.start_sec)
            hi = min(c.end_sec, k.end_sec)
            if hi > lo:
                c_len = c.end_sec - c.start_sec
                k_len = k.end_sec - k.start_sec
                overlap_ratio = (hi - lo) / min(c_len, k_len) if min(c_len, k_len) > 0 else 0
                if overlap_ratio > 0.5:
                    overlap = True
                    break
        if not overlap:
            kept.append(c)
    return kept


def _clip_candidate(c: Candidate, duration: float | None) -> Candidate | None:
    """Reject out-of-range candidates; clip end to duration if known."""
    if c.start_sec < 0 or c.end_sec <= c.start_sec:
        return None
    if duration is not None:
        if c.start_sec >= duration:
            return None
        end = min(c.end_sec, duration)
        return Candidate(
            start_sec=c.start_sec,
            end_sec=end,
            score=c.score,
            source_ref=c.source_ref,
            caption=c.caption,
        )
    return c


async def run_investigation(
    req: InvestigateRequest,
    search_provider: SearchProvider,
    detection_provider: DetectionProvider | None,
    reasoning_provider: ReasoningProvider | None,
    mode: ProviderMode,
    video_duration: float | None,
    search_timeout: float,
    reasoning_timeout: float,
) -> InvestigateResponse:
    trace: list[ToolTraceEntry] = []
    warnings: list[str] = []

    # 1. Resolve session
    session_id = _session_store.get_or_create(req.session_id)

    # 2. Validate selected_event (must belong to same session + same video)
    selected_event: Event | None = None
    if req.selected_event_id:
        selected_event = _session_store.get_event(session_id, req.selected_event_id)
        if selected_event is None:
            raise ValueError(f"selected_event_id {req.selected_event_id!r} not found in session {session_id!r}")
        if selected_event.video_id != req.video_id:
            raise ValueError("selected_event belongs to a different video")

    # 3. Search
    t0 = time.monotonic()
    try:
        if selected_event is not None:
            candidates = await asyncio.wait_for(
                search_provider.expand(
                    req.video_id,
                    selected_event.start_sec,
                    selected_event.end_sec,
                    req.query,
                ),
                timeout=search_timeout,
            )
            search_tool = "expand"
        else:
            candidates = await asyncio.wait_for(
                search_provider.search(req.video_id, req.query, top_k=5),
                timeout=search_timeout,
            )
            search_tool = "search"
    except asyncio.TimeoutError:
        logger.warning("Search provider timed out after %.1f s", search_timeout)
        candidates = []
        warnings.append(f"Search provider timed out after {search_timeout:.0f} s; results may be incomplete.")
        search_tool = "search"
    except Exception as exc:
        logger.error("Search provider error: %s", exc)
        candidates = []
        warnings.append(f"Search provider error: {exc}")
        search_tool = "search"

    elapsed_search = int((time.monotonic() - t0) * 1000)
    trace.append(ToolTraceEntry(tool=search_tool, status="ok" if candidates else "no_results", duration_ms=elapsed_search))

    # 4. Normalize and deduplicate
    valid: list[Candidate] = []
    for c in candidates:
        clipped = _clip_candidate(c, video_duration)
        if clipped:
            valid.append(clipped)
    candidates = _dedup_candidates(valid)[:5]

    # 5. Optional detection
    detections_map: dict[int, list] = {}
    if detection_provider and candidates:
        for i, c in enumerate(candidates[:3]):
            t1 = time.monotonic()
            try:
                dets = await asyncio.wait_for(
                    detection_provider.detect(req.video_id, c.start_sec, c.end_sec),
                    timeout=search_timeout,
                )
                detections_map[i] = dets
            except Exception as exc:
                logger.warning("Detection provider error for candidate %d: %s", i, exc)
                detections_map[i] = []
            elapsed_det = int((time.monotonic() - t1) * 1000)
            trace.append(ToolTraceEntry(tool="detect", status="ok", duration_ms=elapsed_det))

    # 6. Optional reasoning
    reasoning_map: dict[int, str] = {}
    if reasoning_provider and candidates:
        for i, c in enumerate(candidates[:3]):
            t2 = time.monotonic()
            try:
                result = await asyncio.wait_for(
                    reasoning_provider.reason(
                        req.video_id,
                        c.start_sec,
                        c.end_sec,
                        req.query,
                        [c.caption or ""],
                    ),
                    timeout=reasoning_timeout,
                )
                reasoning_map[i] = result.summary
            except Exception as exc:
                logger.warning("Reasoning provider error for candidate %d: %s", i, exc)
                reasoning_map[i] = ""
            elapsed_r = int((time.monotonic() - t2) * 1000)
            trace.append(ToolTraceEntry(tool="reason", status="ok", duration_ms=elapsed_r))

    # 7. Build events
    events: list[Event] = []
    from app.fixtures import lookup as fixture_lookup
    fixture_labels = {f.start_sec: f.labels for f in fixture_lookup(req.query)}

    for i, c in enumerate(candidates):
        evt_id = str(uuid.uuid4())
        evidence: list[EvidenceItem] = [
            EvidenceItem(
                kind="retrieval",
                detail=c.caption or c.source_ref or "Matched segment",
                start_sec=c.start_sec,
                end_sec=c.end_sec,
            )
        ]
        for det in detections_map.get(i, []):
            evidence.append(EvidenceItem(kind="detection", detail=f"{det.label} ({det.confidence:.2f})"))

        reasoning_text = reasoning_map.get(i, "")
        if reasoning_text:
            evidence.append(EvidenceItem(kind="reasoning", detail=reasoning_text))

        labels = [d.label for d in detections_map.get(i, [])]
        if not labels:
            labels = fixture_labels.get(c.start_sec, [])

        explanation = c.caption or "Activity detected in this segment."
        if reasoning_text and not reasoning_text.startswith("[Mock"):
            explanation = reasoning_text

        events.append(
            Event(
                event_id=evt_id,
                video_id=req.video_id,
                start_sec=c.start_sec,
                end_sec=c.end_sec,
                explanation=explanation,
                evidence=evidence,
                labels=labels,
                score=c.score,
                verification=VerificationStatus.unverified_mock if mode == ProviderMode.mock else VerificationStatus.retrieval_only,
            )
        )

    # Store events in session
    _session_store.store_events(session_id, events)

    if mode == ProviderMode.mock:
        warnings.append("Demo fixtures — not live inference. Results are illustrative only.")

    answer = (
        f"Found {len(events)} candidate moment(s) for: \"{req.query}\"."
        if events
        else "No supported evidence found for this query in the demo footage."
    )

    return InvestigateResponse(
        session_id=session_id,
        mode=mode,
        answer=answer,
        events=events,
        tool_trace=trace,
        warnings=warnings,
    )
