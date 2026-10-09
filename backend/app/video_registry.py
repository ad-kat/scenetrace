"""Maps SceneTrace video_id values to VSS original_video URIs."""
from __future__ import annotations

import hashlib
import logging
import threading
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RegistryEntry:
    video_id: str
    original_video: str
    title: str
    duration_sec: float | None
    preview_source: str | None
    location: str | None = None
    camera_id: str | None = None
    filename: str | None = None


def stable_video_id(original_video: str) -> str:
    digest = hashlib.sha1(original_video.encode("utf-8")).hexdigest()[:16]
    return f"vss-{digest}"


class VideoRegistry:
    def __init__(self) -> None:
        self._by_id: dict[str, RegistryEntry] = {}
        self._lock = threading.Lock()

    def clear(self) -> None:
        with self._lock:
            self._by_id.clear()

    def upsert(
        self,
        *,
        original_video: str,
        title: str | None = None,
        duration_sec: float | None = None,
        preview_source: str | None = None,
        location: str | None = None,
        camera_id: str | None = None,
        filename: str | None = None,
    ) -> RegistryEntry:
        vid = stable_video_id(original_video)
        entry = RegistryEntry(
            video_id=vid,
            original_video=original_video,
            title=title or filename or vid,
            duration_sec=duration_sec,
            preview_source=preview_source,
            location=location,
            camera_id=camera_id,
            filename=filename,
        )
        with self._lock:
            self._by_id[vid] = entry
        return entry

    def get(self, video_id: str) -> RegistryEntry | None:
        with self._lock:
            return self._by_id.get(video_id)

    def get_original(self, video_id: str) -> str | None:
        entry = self.get(video_id)
        return entry.original_video if entry else None

    def all(self) -> list[RegistryEntry]:
        with self._lock:
            return list(self._by_id.values())


_registry = VideoRegistry()


def get_registry() -> VideoRegistry:
    return _registry
