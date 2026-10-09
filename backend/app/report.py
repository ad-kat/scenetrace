"""Incident report generator.

Builds a structured, timestamped report from session events stored by the
investigation agent. No LLM required — the report summarises evidence already
retrieved and flags uncertainty explicitly.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.agent import get_session_store
from app.schemas import (
    Event,
    IncidentReport,
    IncidentReportSection,
    VerificationStatus,
)


def _fmt_time(sec: float) -> str:
    m = int(sec // 60)
    s = int(sec % 60)
    return f"{m}:{s:02d}"


def _verification_label(v: VerificationStatus) -> str:
    return {
        VerificationStatus.verified_model: "Model-verified",
        VerificationStatus.retrieval_only: "Retrieval-only (not model-verified)",
        VerificationStatus.unverified_mock: "Demo fixture — not live inference",
    }.get(v, str(v))


def generate_report(
    session_id: str,
    title: str | None = None,
) -> IncidentReport:
    store = get_session_store()
    timeline = store.timeline(session_id)

    # Collect all events across all turns in this session.
    all_events: list[Event] = []
    seen_ids: set[str] = set()
    for turn in timeline:
        for eid in turn.event_ids:
            evt = store.get_event(session_id, eid)
            if evt and eid not in seen_ids:
                all_events.append(evt)
                seen_ids.add(eid)

    generated_at = datetime.now(tz=timezone.utc).isoformat()
    report_title = title or "SceneTrace Incident Investigation Report"

    # Determine overall uncertainty
    has_mock = any(
        e.verification == VerificationStatus.unverified_mock for e in all_events
    )
    has_live = any(
        e.verification != VerificationStatus.unverified_mock for e in all_events
    )

    uncertainty_notes: list[str] = []
    if has_mock:
        uncertainty_notes.append(
            "One or more events are demo fixtures, not live model output. "
            "Treat these as illustrative only."
        )
    if not all_events:
        uncertainty_notes.append(
            "No events were found in this session. The report contains no evidence."
        )
    retrieval_only = [
        e for e in all_events
        if e.verification == VerificationStatus.retrieval_only
    ]
    if retrieval_only:
        uncertainty_notes.append(
            f"{len(retrieval_only)} event(s) are retrieval-only and have not been "
            "confirmed by a reasoning model. Temporal boundaries may be approximate."
        )

    # Source references
    refs: list[str] = []
    for e in all_events:
        src = e.original_video or e.playback_source
        if src and src not in refs:
            refs.append(src)

    # Summary sentence
    if not all_events:
        summary = "No incidents were identified in this investigation session."
    else:
        labels_flat: list[str] = []
        for e in all_events:
            labels_flat.extend(e.labels)
        unique_labels = list(dict.fromkeys(labels_flat))
        label_str = ", ".join(unique_labels) if unique_labels else "unclassified activity"
        summary = (
            f"This investigation identified {len(all_events)} candidate incident moment(s) "
            f"involving {label_str}. "
            f"Evidence was gathered across {len(timeline)} investigation turn(s)."
        )

    # Build narrative sections
    sections: list[IncidentReportSection] = []

    if timeline:
        query_lines = "\n".join(
            f"  Turn {i+1}: \"{t.query}\""
            + (f" (follow-up of prior event)" if t.follow_up_of else "")
            for i, t in enumerate(timeline)
        )
        sections.append(
            IncidentReportSection(
                heading="Investigation Queries",
                content=query_lines,
            )
        )

    if all_events:
        event_lines: list[str] = []
        for i, e in enumerate(all_events):
            line = (
                f"Event {i+1}: [{_fmt_time(e.start_sec)}–{_fmt_time(e.end_sec)}] "
                f"  {e.explanation}\n"
                f"  Labels: {', '.join(e.labels) or 'none'} | "
                f"Verification: {_verification_label(e.verification)}"
            )
            if e.evidence:
                kinds = ", ".join(sorted({ev.kind for ev in e.evidence}))
                line += f" | Evidence types: {kinds}"
            event_lines.append(line)
        sections.append(
            IncidentReportSection(
                heading="Identified Incidents",
                content="\n\n".join(event_lines),
            )
        )

    if refs:
        sections.append(
            IncidentReportSection(
                heading="Source Video References",
                content="\n".join(f"  • {r}" for r in refs),
            )
        )

    if uncertainty_notes:
        sections.append(
            IncidentReportSection(
                heading="Uncertainty and Limitations",
                content="\n".join(f"  • {n}" for n in uncertainty_notes),
            )
        )

    sections.append(
        IncidentReportSection(
            heading="Report Metadata",
            content=(
                f"  Generated: {generated_at}\n"
                f"  Session ID: {session_id}\n"
                f"  Provider mode: {'demo/mock' if has_mock and not has_live else 'live'}"
            ),
        )
    )

    return IncidentReport(
        report_id=str(uuid.uuid4()),
        generated_at=generated_at,
        session_id=session_id,
        title=report_title,
        summary=summary,
        incidents=all_events,
        sections=sections,
        uncertainty_notes=uncertainty_notes,
        source_references=refs,
    )
