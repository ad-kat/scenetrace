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

    # Build findings from actual retrieval and reasoning evidence.
    summary = (
        f"Reviewed {len(all_events)} retrieved video moment(s) across "
        f"{len(timeline)} investigation turn(s). These are candidate "
        "safety observations, not confirmed near-misses."
        if all_events else "No candidate moments were found in this investigation."
    )

    sections: list[IncidentReportSection] = []
    observations, assessments, factors, consequences, prevention = [], [], [], [], []

    for i, e in enumerate(all_events, 1):
        stamp = f"{_fmt_time(e.start_sec)}–{_fmt_time(e.end_sec)}"
        retrieval = " ".join(
            ev.detail for ev in e.evidence
            if ev.kind == "retrieval" and ev.detail
        )
        reasoning = next(
            (ev.detail for ev in e.evidence
             if ev.kind == "reasoning" and ev.detail), ""
        )
        description = retrieval or e.explanation or "No scene description available."
        text = description.lower()

        observations.append(
            f"Finding {i} [{stamp}] | {e.camera_id or 'Unknown camera'}\n"
            f"Source: {e.filename or e.original_video or 'Unavailable'}\n"
            f"Observed scene: {description}\n"
            f"Analysis: {reasoning[:900] if reasoning else 'No model reasoning available.'}\n"
            f"Evidence status: {_verification_label(e.verification)}"
        )

        stopped = any(x in text for x in (
            "cyclist is stopped", "rider is stopped",
            "vehicle is stopped", "cyclist is stationary"
        ))
        obstruction = any(x in text for x in (
            "blocking the road", "blocking the lane",
            "partially blocking", "obstruct", "barrier",
            "barricade", "narrow gap", "narrow passage"
        ))
        moving_conflict = any(x in text for x in (
            "swerv", "brak", "avoid a collision",
            "almost collided", "narrowly missed",
            "close pass", "crossing in front",
            "entered the path"
        ))
        bike = any(x in text for x in (
            "cyclist", "bicycle", "bike lane", "rider"
        ))

        if moving_conflict:
            assessment = "Possible movement conflict worth reviewing."
        elif obstruction:
            assessment = "Roadway obstruction or restricted passage; potential hazard."
        else:
            assessment = "No clear near-miss established by the retrieved description."

        if stopped and not moving_conflict:
            assessment += " The described rider or vehicle is stopped."

        assessments.append(f"Finding {i} [{stamp}]: {assessment}")

        if obstruction:
            factors.append(
                f"Finding {i} [{stamp}]: The described obstruction may reduce "
                "available clearance or visibility. Actual distances are unknown."
            )
            consequences.append(
                f"Finding {i} [{stamp}]: If a moving rider encounters this "
                "restriction without sufficient clearance, a collision with "
                "an obstacle or nearby road user could become possible."
            )
            prevention.append(
                f"Finding {i} [{stamp}]: Reduce approach speed before the "
                "obstruction, check for approaching traffic, and proceed "
                "only if sufficient passing clearance is available."
            )
        elif moving_conflict:
            factors.append(
                f"Finding {i} [{stamp}]: Review the visible trajectories, "
                "available separation, visibility, and opportunity to react. "
                "The actual speed is not measured."
            )
            consequences.append(
                f"Finding {i} [{stamp}]: Conflicting movement could create "
                "collision risk if clearance or reaction time is insufficient."
            )
            prevention.append(
                f"Finding {i} [{stamp}]: Adjust speed to the available "
                "visibility, preserve clearance, anticipate movements by "
                "other road users, and avoid sudden unsafe maneuvers."
            )
        elif bike:
            factors.append(
                f"Finding {i} [{stamp}]: No specific hazardous interaction "
                "is established. Review available space and visibility."
            )
            consequences.append(
                f"Finding {i} [{stamp}]: No concrete accident consequence "
                "can be attributed to this segment from the available evidence."
            )
            prevention.append(
                f"Finding {i} [{stamp}]: General cycling precautions include "
                "maintaining a speed appropriate to sightlines and road "
                "conditions and keeping adequate clearance. This is "
                "general advice, not a finding of unsafe riding."
            )
        else:
            factors.append(
                f"Finding {i} [{stamp}]: Insufficient evidence to identify "
                "a specific contributing factor."
            )
            consequences.append(
                f"Finding {i} [{stamp}]: No supported incident-specific "
                "consequence identified."
            )
            prevention.append(
                f"Finding {i} [{stamp}]: Review the original footage before "
                "making an incident-specific safety recommendation."
            )

    for heading, lines in [
        ("A. Observed Behavior", observations),
        ("B. Potential Near-Miss Assessment", assessments),
        ("C. Possible Contributing Factors", factors),
        ("D. Possible Consequences", consequences),
        ("E. Preventive Recommendations", prevention),
    ]:
        sections.append(IncidentReportSection(
            heading=heading,
            content="\n\n".join(lines) if lines else "No supported findings available.",
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
