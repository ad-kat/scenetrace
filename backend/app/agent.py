"""Deterministic orchestration state machine for investigation requests."""
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
from app.providers.cosmos import CosmosReasoningProvider
from app.providers.vast import VastSearchProvider
from app.providers.yolo import YoloDetectionProvider
from app.schemas import (
    EvidenceItem,
    Event,
    InvestigateRequest,
    InvestigateResponse,
    ProviderMode,
    TimelineEntry,
    ToolTraceEntry,
    VerificationStatus,
)
from app.video_registry import get_registry

logger = logging.getLogger(__name__)

_FOLLOW_UP_WINDOW_SEC = 15.0


@dataclass
class SessionStore:
    """In-memory session store. Not durable across restarts."""

    _events: dict[str, dict[str, Event]] = field(default_factory=dict)
    _timeline: dict[str, list[TimelineEntry]] = field(default_factory=dict)

    def get_or_create(self, session_id: str | None) -> str:
        if not session_id or session_id not in self._events:
            sid = str(uuid.uuid4())
            self._events[sid] = {}
            self._timeline[sid] = []
            return sid
        return session_id

    def store_events(self, session_id: str, events: list[Event]) -> None:
        self._events.setdefault(session_id, {})
        for evt in events:
            self._events[session_id][evt.event_id] = evt

    def get_event(self, session_id: str, event_id: str) -> Event | None:
        return self._events.get(session_id, {}).get(event_id)

    def append_timeline(self, session_id: str, entry: TimelineEntry) -> None:
        self._timeline.setdefault(session_id, []).append(entry)

    def timeline(self, session_id: str) -> list[TimelineEntry]:
        return list(self._timeline.get(session_id, []))


_session_store = SessionStore()


def get_session_store() -> SessionStore:
    return _session_store


def _dedup_candidates(candidates: list[Candidate]) -> list[Candidate]:
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
            original_video=c.original_video,
            object_classes=list(c.object_classes),
            extra=dict(c.extra),
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

    session_id = _session_store.get_or_create(req.session_id)

    selected_event: Event | None = None
    if req.selected_event_id:
        selected_event = _session_store.get_event(session_id, req.selected_event_id)
        if selected_event is None:
            raise ValueError(
                f"selected_event_id {req.selected_event_id!r} not found in session {session_id!r}"
            )
        if selected_event.video_id != req.video_id:
            raise ValueError("selected_event belongs to a different video")

    registry = get_registry()
    entry = registry.get(req.video_id)
    original_video = (
        (selected_event.original_video if selected_event else None)
        or (entry.original_video if entry else None)
    )

    # --- Search / expand -------------------------------------------------
    t0 = time.monotonic()
    candidates: list[Candidate] = []
    grounded_answer: str | None = None
    try:
        if selected_event is not None:
            expand_kwargs = {}
            if isinstance(search_provider, VastSearchProvider):
                expand_kwargs = {
                    "original_video": original_video or selected_event.original_video,
                    "window_sec": _FOLLOW_UP_WINDOW_SEC,
                }
            candidates = await asyncio.wait_for(
                search_provider.expand(  # type: ignore[call-arg]
                    req.video_id,
                    selected_event.start_sec,
                    selected_event.end_sec,
                    req.query,
                    **expand_kwargs,
                ),
                timeout=search_timeout,
            )
            search_tool = "expand"
        else:
            search_kwargs = {}
            if isinstance(search_provider, VastSearchProvider):
                search_kwargs = {
                    "original_video": original_video,
                    "object_classes": req.object_classes,
                    "metadata_filters": req.metadata_filters,
                }
            candidates = await asyncio.wait_for(
                search_provider.search(  # type: ignore[call-arg]
                    req.video_id,
                    req.query,
                    top_k=5,
                    **search_kwargs,
                ),
                timeout=search_timeout,
            )
            search_tool = "search"
            if isinstance(search_provider, VastSearchProvider):
                grounded_answer = await search_provider.grounded_answer(
                    req.query,
                    original_video=original_video,
                    object_classes=req.object_classes,
                    top_k=5,
                )
    except asyncio.TimeoutError:
        logger.warning("Search provider timed out after %.1f s", search_timeout)
        candidates = []
        warnings.append(
            f"Search provider timed out after {search_timeout:.0f} s; results may be incomplete."
        )
        search_tool = "search"
    except Exception as exc:
        logger.error("Search provider error: %s", exc)
        candidates = []
        warnings.append(f"Search provider error: {exc}")
        search_tool = "search"

    elapsed_search = int((time.monotonic() - t0) * 1000)
    trace.append(
        ToolTraceEntry(
            tool=search_tool,
            status="ok" if candidates else "no_results",
            duration_ms=elapsed_search,
        )
    )

    valid: list[Candidate] = []
    for c in candidates:
        clipped = _clip_candidate(c, video_duration)
        if clipped:
            # Prefer registry original_video when candidate omitted it.
            if not clipped.original_video and original_video:
                clipped.original_video = original_video
            valid.append(clipped)
    candidates = _dedup_candidates(valid)[:5]

    # Optional client-side object filter when metadata filter was not applied.
    if req.object_classes:
        wanted = {o.lower() for o in req.object_classes}
        filtered = [
            c
            for c in candidates
            if not c.object_classes
            or any(o.lower() in wanted for o in c.object_classes)
        ]
        if filtered:
            candidates = filtered
        else:
            warnings.append(
                "No candidates matched object_classes filter; showing unfiltered retrieval hits."
            )

    # --- Detections ------------------------------------------------------
    detections_map: dict[int, list] = {}
    if detection_provider and candidates:
        for i, c in enumerate(candidates[:3]):
            t1 = time.monotonic()
            try:
                if isinstance(detection_provider, YoloDetectionProvider):
                    dets = await asyncio.wait_for(
                        detection_provider.detect(
                            req.video_id,
                            c.start_sec,
                            c.end_sec,
                            source=c.source_ref,
                        ),
                        timeout=search_timeout,
                    )
                else:
                    dets = await asyncio.wait_for(
                        detection_provider.detect(
                            req.video_id, c.start_sec, c.end_sec
                        ),
                        timeout=search_timeout,
                    )
                detections_map[i] = dets
                status = "ok" if dets else "empty"
            except Exception as exc:
                logger.warning("Detection provider error for candidate %d: %s", i, exc)
                detections_map[i] = []
                status = "error"
            elapsed_det = int((time.monotonic() - t1) * 1000)
            trace.append(
                ToolTraceEntry(tool="detect", status=status, duration_ms=elapsed_det)
            )

    # --- Reasoning -------------------------------------------------------
    reasoning_map: dict[int, str] = {}
    if reasoning_provider and candidates and mode != ProviderMode.mock:
        for i, c in enumerate(candidates[:2]):
            t2 = time.monotonic()
            try:
                if isinstance(reasoning_provider, CosmosReasoningProvider):
                    reasoning_provider.set_original_video(
                        c.original_video or original_video
                    )
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
                reasoning_map[i] = result.summary if result.supported else ""
                status = "ok" if result.supported else "unsupported"
            except Exception as exc:
                logger.warning("Reasoning provider error for candidate %d: %s", i, exc)
                reasoning_map[i] = ""
                status = "error"
            elapsed_r = int((time.monotonic() - t2) * 1000)
            trace.append(
                ToolTraceEntry(tool="reason", status=status, duration_ms=elapsed_r)
            )
    elif reasoning_provider and mode == ProviderMode.mock and candidates:
        # Keep mock reasoning in the trace for demo mode.
        for i, c in enumerate(candidates[:1]):
            t2 = time.monotonic()
            result = await reasoning_provider.reason(
                req.video_id, c.start_sec, c.end_sec, req.query, [c.caption or ""]
            )
            reasoning_map[i] = result.summary
            elapsed_r = int((time.monotonic() - t2) * 1000)
            trace.append(
                ToolTraceEntry(tool="reason", status="ok", duration_ms=elapsed_r)
            )

    # --- Build events ----------------------------------------------------
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
            evidence.append(
                EvidenceItem(
                    kind="detection",
                    detail=f"{det.label} ({det.confidence:.2f})",
                    start_sec=det.start_sec,
                    end_sec=det.end_sec,
                )
            )

        reasoning_text = reasoning_map.get(i, "")
        if reasoning_text:
            evidence.append(EvidenceItem(kind="reasoning", detail=reasoning_text))

        labels = [d.label for d in detections_map.get(i, [])]
        if not labels:
            labels = list(c.object_classes)
        if not labels and mode == ProviderMode.mock:
            labels = fixture_labels.get(c.start_sec, [])

        explanation = c.caption or "Activity detected in this segment."
        if reasoning_text and not reasoning_text.startswith("[Mock"):
            # Prefer short retrieval caption on the card; full answer goes top-level.
            explanation = c.caption or reasoning_text[:400]

        if mode == ProviderMode.mock:
            verification = VerificationStatus.unverified_mock
        elif reasoning_map.get(i):
            verification = VerificationStatus.verified_model
        else:
            verification = VerificationStatus.retrieval_only

        loc = c.extra.get("location") or (entry.location if entry else None)
        cam = c.extra.get("camera_id") or (entry.camera_id if entry else None)
        fname = c.extra.get("filename") or (entry.filename if entry else None)

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
                verification=verification,
                playback_source=c.source_ref,
                original_video=c.original_video or original_video,
                location=str(loc) if loc else None,
                camera_id=str(cam) if cam else None,
                filename=str(fname) if fname else None,
            )
        )

    _session_store.store_events(session_id, events)

    turn = TimelineEntry(
        turn_id=str(uuid.uuid4()),
        query=req.query,
        event_ids=[e.event_id for e in events],
        answer_preview=(grounded_answer or "")[:240],
        follow_up_of=selected_event.event_id if selected_event else None,
    )
    _session_store.append_timeline(session_id, turn)

    if mode == ProviderMode.mock:
        warnings.append(
            "Demo fixtures — not live inference. Results are illustrative only."
        )

    if grounded_answer:
        answer = grounded_answer
    elif events:
        answer = f"Found {len(events)} candidate moment(s) for: \"{req.query}\"."
    else:
        answer = "No supported evidence found for this query."

    return InvestigateResponse(
        session_id=session_id,
        mode=mode,
        answer=answer,
        events=events,
        tool_trace=trace,
        warnings=warnings,
        timeline=_session_store.timeline(session_id),
    )
