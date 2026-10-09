"""Video registry and media path management (demo + live VSS explore)."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from app.config import get_settings
from app.providers.vss_client import VssClient
from app.schemas import VideoInfo
from app.video_registry import get_registry

logger = logging.getLogger(__name__)

_ALLOWED_DEMO_IDS: set[str] = {"demo-01"}


def _probe_duration(path: Path) -> float | None:
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


def _demo_videos() -> list[VideoInfo]:
    settings = get_settings()
    media_dir = settings.scenetrace_media_dir
    path = media_dir / "demo-01.mp4"
    duration = _probe_duration(path) if path.exists() else None
    video_url = "/api/videos/demo-01/file" if path.exists() else ""
    return [
        VideoInfo(
            id="demo-01",
            title="SceneTrace Demo Footage",
            duration_sec=duration,
            video_url=video_url,
            source="demo",
        )
    ]


async def load_vss_videos(client: VssClient, *, limit: int | None = None) -> list[VideoInfo]:
    settings = get_settings()
    lim = limit or settings.explore_limit
    registry = get_registry()
    data = await client.explore(limit=lim, offset=0)
    chunks = list(data.get("chunks") or [])
    videos: list[VideoInfo] = []
    for chunk in chunks:
        original = chunk.get("original_video")
        if not isinstance(original, str) or not original:
            continue
        filename = chunk.get("filename")
        location = chunk.get("location")
        camera_id = chunk.get("camera_id")
        duration = chunk.get("chunk_duration_sec")
        try:
            duration_f = float(duration) if duration is not None else None
        except (TypeError, ValueError):
            duration_f = None
        title_bits = [filename or "Indexed clip"]
        if location:
            title_bits.append(str(location))
        if camera_id:
            title_bits.append(str(camera_id))
        entry = registry.upsert(
            original_video=original,
            title=" · ".join(title_bits),
            duration_sec=duration_f,
            preview_source=chunk.get("preview_source"),
            location=str(location) if location else None,
            camera_id=str(camera_id) if camera_id else None,
            filename=str(filename) if filename else None,
        )
        videos.append(
            VideoInfo(
                id=entry.video_id,
                title=entry.title,
                duration_sec=entry.duration_sec,
                video_url=f"/api/videos/{entry.video_id}/file",
                source="vss",
                location=entry.location,
                camera_id=entry.camera_id,
                original_video=entry.original_video,
            )
        )
    return videos


def get_video_list() -> list[VideoInfo]:
    """Synchronous demo list (mock / always available)."""
    return _demo_videos()


async def get_video_list_async(client: VssClient | None) -> list[VideoInfo]:
    settings = get_settings()
    if settings.scenetrace_mode == "mock" or client is None:
        return _demo_videos()
    try:
        live = await load_vss_videos(client)
        if settings.scenetrace_mode == "hybrid":
            return _demo_videos() + live
        return live or _demo_videos()
    except Exception as exc:
        logger.error("Failed to load VSS explore list: %s", exc)
        if settings.scenetrace_mode == "live":
            raise
        return _demo_videos()


def resolve_video_path(video_id: str) -> Path:
    if video_id not in _ALLOWED_DEMO_IDS:
        raise ValueError(f"Unknown video_id: {video_id!r}")
    settings = get_settings()
    return settings.scenetrace_media_dir / f"{video_id}.mp4"


def is_valid_video_id(video_id: str, client: VssClient | None = None) -> bool:
    if video_id in _ALLOWED_DEMO_IDS:
        return True
    if video_id.startswith("vss-") and get_registry().get(video_id) is not None:
        return True
    return False


def ensure_video_known(video_id: str) -> bool:
    """True if demo or already registered from explore/search."""
    if video_id in _ALLOWED_DEMO_IDS:
        return True
    return get_registry().get(video_id) is not None
