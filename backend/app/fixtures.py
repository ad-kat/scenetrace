"""Deterministic demo fixtures keyed by query patterns.

These are annotated simulation events for the generated demo video (120 s).
Every timestamp is valid for a 120-second source. Never present these as
real model output; they carry verification='unverified_mock'.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FixtureEvent:
    start_sec: float
    end_sec: float
    explanation: str
    labels: list[str]
    caption: str


@dataclass(frozen=True)
class ArchiveFixture:
    """Simulates an archive-wide search result from a different camera/location."""
    video_title: str
    location: str
    camera_id: str
    start_sec: float
    end_sec: float
    score: float
    caption: str
    labels: list[str] = field(default_factory=list)


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
    "forklift": [
        FixtureEvent(
            start_sec=33.0,
            end_sec=42.0,
            explanation=(
                "Potential near-miss: a forklift is operating in close proximity "
                "to a worker in the aisle. Minimum safe separation may be insufficient."
            ),
            labels=["forklift", "person"],
            caption="Forklift-worker proximity — potential near-miss (demo fixture)",
        ),
        FixtureEvent(
            start_sec=78.0,
            end_sec=86.0,
            explanation=(
                "Potential near-miss: a forklift moves through a zone where a "
                "worker is stationary. Worker appears to be in the travel path."
            ),
            labels=["forklift", "person"],
            caption="Forklift incursion into worker zone — potential near-miss (demo fixture)",
        ),
    ],
    "safety": [
        FixtureEvent(
            start_sec=33.0,
            end_sec=42.0,
            explanation=(
                "Potential near-miss: forklift-worker proximity event detected. "
                "Minimum safe separation may be violated. Requires human verification."
            ),
            labels=["forklift", "person"],
            caption="Safety proximity event (demo fixture)",
        ),
    ],
    "vehicle": [
        FixtureEvent(
            start_sec=88.0,
            end_sec=97.0,
            explanation="A moving object consistent with a small vehicle passes through the frame.",
            labels=["vehicle"],
            caption="Vehicle in frame (demo fixture)",
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

# Archive-wide mock search results per query pattern.
ARCHIVE_FIXTURE_MAP: dict[str, list[ArchiveFixture]] = {
    "forklift": [
        ArchiveFixture(
            video_title="Warehouse Aisle 3 · CAM-07",
            location="Aisle 3",
            camera_id="CAM-07",
            start_sec=33.0,
            end_sec=42.0,
            score=0.91,
            caption=(
                "Forklift operating with a pedestrian in close proximity. "
                "Worker appears to step into the travel path."
            ),
            labels=["forklift", "person"],
        ),
        ArchiveFixture(
            video_title="Loading Bay · CAM-02",
            location="Loading Bay",
            camera_id="CAM-02",
            start_sec=78.0,
            end_sec=86.0,
            score=0.84,
            caption=(
                "Forklift reversing while worker stands behind it without visibility of the vehicle."
            ),
            labels=["forklift", "person"],
        ),
        ArchiveFixture(
            video_title="Cross-Aisle Junction · CAM-11",
            location="Cross-Aisle Junction",
            camera_id="CAM-11",
            start_sec=14.0,
            end_sec=22.0,
            score=0.77,
            caption="Forklift and pedestrian approaching a blind corner from opposite directions.",
            labels=["forklift", "person"],
        ),
    ],
    "pedestrian": [
        ArchiveFixture(
            video_title="Main Corridor · CAM-01",
            location="Main Corridor",
            camera_id="CAM-01",
            start_sec=5.0,
            end_sec=14.0,
            score=0.88,
            caption="Pedestrian crossing a vehicle travel lane without checking for traffic.",
            labels=["person"],
        ),
        ArchiveFixture(
            video_title="Warehouse Aisle 3 · CAM-07",
            location="Aisle 3",
            camera_id="CAM-07",
            start_sec=65.0,
            end_sec=72.0,
            score=0.79,
            caption="Worker standing in marked vehicle travel zone during active shift.",
            labels=["person"],
        ),
    ],
    "vehicle": [
        ArchiveFixture(
            video_title="Yard Gate · CAM-05",
            location="Yard Gate",
            camera_id="CAM-05",
            start_sec=88.0,
            end_sec=97.0,
            score=0.85,
            caption="Heavy vehicle exiting yard while a pedestrian approaches the gate from the side.",
            labels=["vehicle", "person"],
        ),
    ],
    "default": [
        ArchiveFixture(
            video_title="Warehouse Aisle 3 · CAM-07",
            location="Aisle 3",
            camera_id="CAM-07",
            start_sec=20.0,
            end_sec=28.0,
            score=0.72,
            caption="Activity detected in segment matching query terms. Requires review.",
            labels=[],
        ),
    ],
}


def lookup(query: str) -> list[FixtureEvent]:
    q = query.lower()
    for key, events in FIXTURE_MAP.items():
        if key != "default" and key in q:
            return events
    return FIXTURE_MAP["default"]


def archive_lookup(query: str) -> list[ArchiveFixture]:
    q = query.lower()
    for key, results in ARCHIVE_FIXTURE_MAP.items():
        if key != "default" and key in q:
            return results
    return ARCHIVE_FIXTURE_MAP["default"]
