"""Video registry and media path management."""
from __future__ import annotations

import subprocess
from pathlib import Path

from app.config import get_settings
from app.schemas import VideoInfo

_ALLOWED_VIDEO_IDS: set[str] = {"demo-01"}


def _probe_duration(path: Path) -> float | None:
    """Use ffprobe to get duration. Returns None on failure."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            shell=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return float(result.stdout.strip())
    except Exception:
        pass
    return None


def get_video_list() -> list[VideoInfo]:
    settings = get_settings()
    media_dir = settings.scenetrace_media_dir
    videos: list[VideoInfo] = []

    path = media_dir / "demo-01.mp4"
    duration = _probe_duration(path) if path.exists() else None

    if path.exists():
        video_url = "/api/videos/demo-01/file"
    else:
        video_url = ""

    videos.append(
        VideoInfo(
            id="demo-01",
            title="SceneTrace Demo Footage",
            duration_sec=duration,
            video_url=video_url,
            source="demo",
        )
    )
    return videos


def resolve_video_path(video_id: str) -> Path:
    """Return the filesystem path for a whitelisted video ID.

    Raises ValueError for non-whitelisted IDs to prevent path traversal.
    """
    if video_id not in _ALLOWED_VIDEO_IDS:
        raise ValueError(f"Unknown video_id: {video_id!r}")
    settings = get_settings()
    return settings.scenetrace_media_dir / f"{video_id}.mp4"


def is_valid_video_id(video_id: str) -> bool:
    return video_id in _ALLOWED_VIDEO_IDS
