"""Safety Investigation Report generator.

Builds a structured, timestamped near-miss report from session events.
All claims are grounded in retrieved evidence. Uncertainty is flagged explicitly.
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

    all_events: list[Event] = []
    seen_ids: set[str] = set()
    for turn in timeline:
        for eid in turn.event_ids:
            evt = store.get_event(session_id, eid)
            if evt and eid not in seen_ids:
                all_events.append(evt)
                seen_ids.add(eid)

    generated_at = datetime.now(tz=timezone.utc).isoformat()
    report_title = title or "SceneTrace Safety Investigation Report"

    has_mock = any(e.verification == VerificationStatus.unverified_mock for e in all_events)
    has_live = any(e.verification != VerificationStatus.unverified_mock for e in all_events)

    uncertainty_notes: list[str] = []
    if has_mock:
        uncertainty_notes.append(
            "One or more findings are demo fixtures, not live model output. "
            "Treat these as illustrative only."
        )
    if not all_events:
        uncertainty_notes.append("No events were found in this session.")
    retrieval_only = [
        e for e in all_events if e.verification == VerificationStatus.retrieval_only
    ]
    if retrieval_only:
        uncertainty_notes.append(
            f"{len(retrieval_only)} finding(s) are retrieval-only and have not been "
            "confirmed by a reasoning model. Temporal boundaries may be approximate."
        )
    uncertainty_notes.append(
        "This report does not assert verified causes, distances, speeds, or human intentions. "
        "All findings require human review before any enforcement or disciplinary action."
    )

    refs: list[str] = []
    for e in all_events:
        src = e.original_video or e.playback_source
        if src and src not in refs:
            refs.append(src)

    # Observed behavior summary
    if not all_events:
        summary = "No near-miss candidates were identified in this investigation session."
    else:
        labels_flat: list[str] = []
        for e in all_events:
            labels_flat.extend(e.labels)
        unique_labels = list(dict.fromkeys(labels_flat))
        label_str = ", ".join(unique_labels) if unique_labels else "unclassified activity"
        summary = (
            f"Investigation identified {len(all_events)} potential near-miss candidate(s) "
            f"involving {label_str}, across {len(timeline)} investigation turn(s). "
            "All findings require human verification."
        )

    sections: list[IncidentReportSection] = []

    # A. Observed behavior
    if all_events:
        obs_lines: list[str] = []
        for i, e in enumerate(all_events):
            loc_str = f" [{e.location or ''}{(' · ' + e.camera_id) if e.camera_id else ''}]".rstrip(" ·[]")
            line = (
                f"Finding {i+1}: [{_fmt_time(e.start_sec)}–{_fmt_time(e.end_sec)}]{loc_str}\n"
                f"  {e.explanation}\n"
                f"  Detected objects: {', '.join(e.labels) or 'none'}\n"
                f"  Verification: {_verification_label(e.verification)}"
            )
            if e.evidence:
                for ev in e.evidence:
                    if ev.kind == "reasoning" and ev.detail:
                        line += f"\n  Reasoning: {ev.detail[:500]}"
                        break
            obs_lines.append(line)
        sections.append(IncidentReportSection(
            heading="A. Observed Behavior",
            content="\n\n".join(obs_lines),
        ))

    # B. Potential near-miss assessment
    nearmiss_lines: list[str] = []
    for i, e in enumerate(all_events):
        has_forklift = any("forklift" in l.lower() for l in e.labels)
        has_person = any(l.lower() in ("person", "pedestrian", "worker") for l in e.labels)
        has_vehicle = any("vehicle" in l.lower() for l in e.labels)
        if has_forklift and has_person:
            assessment = (
                "Forklift and person detected in the same segment. "
                "This is a potential near-miss: a forklift operating in proximity to a pedestrian "
                "without confirmed safe separation. Requires human verification of actual distance and intent."
            )
        elif has_vehicle and has_person:
            assessment = (
                "Vehicle and person detected in the same segment. "
                "Potential hazardous interaction — requires review of relative trajectories."
            )
        elif e.labels:
            assessment = (
                f"Objects detected: {', '.join(e.labels)}. "
                "Whether a near-miss occurred requires human review of the footage."
            )
        else:
            assessment = "No specific near-miss pattern identified from available detections."
        nearmiss_lines.append(f"Finding {i+1} [{_fmt_time(e.start_sec)}–{_fmt_time(e.end_sec)}]: {assessment}")
    if nearmiss_lines:
        sections.append(IncidentReportSection(
            heading="B. Potential Near-Miss Assessment",
            content="\n\n".join(nearmiss_lines),
        ))

    # C. Possible contributing factors
    factor_lines = [
        "Possible contributing factors — these are hypotheses for human review, not verified causes:",
        "  • Shared pedestrian-vehicle pathways without physical separation",
        "  • Reduced sightlines at aisle intersections or loading zones",
        "  • Forklift travel routes overlapping with pedestrian access areas",
        "  • Absence of visible warning signals or audible alerts in retrieved footage",
        "  • Worker positioned outside marked safety zones (if applicable — verify in footage)",
    ]
    sections.append(IncidentReportSection(
        heading="C. Possible Contributing Factors",
        content="\n".join(factor_lines),
    ))

    # D. Possible consequences
    sections.append(IncidentReportSection(
        heading="D. Possible Consequences",
        content=(
            "If a similar situation were to escalate without intervention:\n"
            "  • Worker-forklift collision leading to serious injury\n"
            "  • Vehicle strike of a pedestrian in a shared traffic zone\n"
            "  • Property damage from unexpected vehicle maneuvers\n"
            "Note: SceneTrace does not assert that any of these consequences occurred or are certain."
        ),
    ))

    # E. Preventive recommendations
    sections.append(IncidentReportSection(
        heading="E. Preventive Recommendations",
        content=(
            "Recommendations for safety team review (not prescriptive — verify against site conditions):\n"
            "  • Review pedestrian-forklift separation protocols in the identified zones\n"
            "  • Inspect physical barriers, floor markings, and sightline obstructions at these locations\n"
            "  • Review operator proximity alert and speed-limit compliance in active zones\n"
            "  • Consider adding camera coverage at blind corners or high-traffic intersections\n"
            "  • Schedule a safety walkthrough of the locations identified in this report"
        ),
    ))

    # F. Evidence and uncertainty
    if refs:
        sections.append(IncidentReportSection(
            heading="F. Source Evidence",
            content="Source video references:\n" + "\n".join(f"  • {r}" for r in refs),
        ))

    if uncertainty_notes:
        sections.append(IncidentReportSection(
            heading="F. Uncertainty and Limitations",
            content="\n".join(f"  • {n}" for n in uncertainty_notes),
        ))

    # Queries
    if timeline:
        sections.append(IncidentReportSection(
            heading="Investigation Queries",
            content="\n".join(
                f"  Turn {i+1}: \"{t.query}\""
                + (" (follow-up)" if t.follow_up_of else "")
                for i, t in enumerate(timeline)
            ),
        ))

    sections.append(IncidentReportSection(
        heading="Report Metadata",
        content=(
            f"  Generated: {generated_at}\n"
            f"  Session ID: {session_id}\n"
            f"  Provider mode: {'demo/mock' if has_mock and not has_live else 'live'}\n"
            f"  Total findings: {len(all_events)}"
        ),
    ))

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
