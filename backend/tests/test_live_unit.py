"""Unit tests that do not require live VSS (mock path + helpers)."""
from __future__ import annotations

from app.providers.vast import _normalize_classes, _row_to_candidate
from app.video_registry import VideoRegistry, stable_video_id


def test_stable_video_id_is_deterministic():
    a = stable_video_id("s3://bucket/a.mp4")
    b = stable_video_id("s3://bucket/a.mp4")
    c = stable_video_id("s3://bucket/b.mp4")
    assert a == b
    assert a != c
    assert a.startswith("vss-")


def test_registry_roundtrip():
    reg = VideoRegistry()
    entry = reg.upsert(
        original_video="s3://team-34-vss-chunks/team-34/x.mp4",
        title="x",
        duration_sec=12.0,
        preview_source="s3://segments/x_seg.mp4",
        location="warehouse3",
    )
    assert reg.get(entry.video_id) is not None
    assert reg.get_original(entry.video_id) == "s3://team-34-vss-chunks/team-34/x.mp4"


def test_row_to_candidate_timing():
    cand = _row_to_candidate(
        {
            "segment_start_sec": 5.0,
            "segment_end_sec": 10.0,
            "similarity_score": 0.51,
            "source": "s3://seg/a.mp4",
            "reasoning_content": "A person near a forklift.",
            "original_video": "s3://chunks/a.mp4",
            "object_classes": "person",
        }
    )
    assert cand is not None
    assert cand.start_sec == 5.0
    assert cand.end_sec == 10.0
    assert cand.object_classes == ["person"]


def test_normalize_classes():
    assert _normalize_classes("person") == ["person"]
    assert _normalize_classes(["person", "forklift"]) == ["person", "forklift"]
    assert _normalize_classes(None) == []
