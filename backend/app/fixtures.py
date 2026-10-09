"""Deterministic demo fixtures keyed by query patterns.

These are annotated simulation events for the generated demo video (120 s).
Every timestamp is valid for a 120-second source. Never present these as
real model output; they carry verification='unverified_mock'.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FixtureEvent:
    start_sec: float
    end_sec: float
    explanation: str
    labels: list[str]
    caption: str


# Pattern → list of fixture events (checked via simple substring match)
FIXTURE_MAP: dict[str, list[FixtureEvent]] = {
    "box": [
        FixtureEvent(
            start_sec=12.0,
            end_sec=19.5,
            explanation="An object consistent with a box is placed on a surface.",
            labels=["box"],
            caption="Box set-down candidate (demo fixture)",
        ),
        FixtureEvent(
            start_sec=47.0,
            end_sec=54.0,
            explanation="A second placement event is visible in the lower frame.",
            labels=["box"],
            caption="Second box placement candidate (demo fixture)",
        ),
    ],
    "person": [
        FixtureEvent(
            start_sec=5.0,
            end_sec=14.0,
            explanation="A figure enters the scene from the left.",
            labels=["person"],
            caption="Person entry candidate (demo fixture)",
        ),
        FixtureEvent(
            start_sec=65.0,
            end_sec=72.0,
            explanation="A figure is stationary near the center.",
            labels=["person"],
            caption="Stationary person candidate (demo fixture)",
        ),
    ],
    "door": [
        FixtureEvent(
            start_sec=30.0,
            end_sec=37.0,
            explanation="A door-like motion is detected in the right frame region.",
            labels=["door"],
            caption="Door motion candidate (demo fixture)",
        ),
    ],
    "vehicle": [
        FixtureEvent(
            start_sec=88.0,
            end_sec=97.0,
            explanation="A moving object consistent with a small vehicle passes through.",
            labels=["vehicle"],
            caption="Vehicle candidate (demo fixture)",
        ),
    ],
    "default": [
        FixtureEvent(
            start_sec=20.0,
            end_sec=28.0,
            explanation="Activity detected in this segment matching query terms.",
            labels=[],
            caption="Generic activity candidate (demo fixture)",
        ),
    ],
}


def lookup(query: str) -> list[FixtureEvent]:
    q = query.lower()
    for key, events in FIXTURE_MAP.items():
        if key != "default" and key in q:
            return events
    return FIXTURE_MAP["default"]
