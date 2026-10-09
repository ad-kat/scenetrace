"""Abstract provider interfaces. Never invent live endpoints here."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


class ProviderNotConfigured(Exception):
    """Raised when a live provider is requested but not configured."""


@dataclass
class Candidate:
    start_sec: float
    end_sec: float
    score: float | None = None
    source_ref: str | None = None
    caption: str | None = None


@dataclass
class Detection:
    label: str
    confidence: float
    start_sec: float
    end_sec: float
    bbox: list[float] = field(default_factory=list)


@dataclass
class ReasoningResult:
    summary: str
    supported: bool
    detail: str = ""


@runtime_checkable
class SearchProvider(Protocol):
    async def search(self, video_id: str, query: str, top_k: int = 5) -> list[Candidate]: ...
    async def expand(self, video_id: str, start_sec: float, end_sec: float, query: str) -> list[Candidate]: ...


@runtime_checkable
class DetectionProvider(Protocol):
    async def detect(self, video_id: str, start_sec: float, end_sec: float) -> list[Detection]: ...


@runtime_checkable
class ReasoningProvider(Protocol):
    async def reason(
        self,
        video_id: str,
        start_sec: float,
        end_sec: float,
        question: str,
        evidence: list[str],
    ) -> ReasoningResult: ...
