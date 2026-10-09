"""Deterministic mock providers. Clearly labeled as simulation."""
from __future__ import annotations

import asyncio

from app.fixtures import lookup
from app.providers.base import Candidate, Detection, ReasoningResult


class MockSearchProvider:
    """Returns fixture candidates keyed by query pattern."""

    async def search(self, video_id: str, query: str, top_k: int = 5) -> list[Candidate]:
        await asyncio.sleep(0)  # yield to event loop; zero real latency
        fixtures = lookup(query)
        return [
            Candidate(
                start_sec=f.start_sec,
                end_sec=f.end_sec,
                score=None,
                source_ref="demo-fixture",
                caption=f.caption,
            )
            for f in fixtures[:top_k]
        ]

    async def expand(
        self, video_id: str, start_sec: float, end_sec: float, query: str
    ) -> list[Candidate]:
        await asyncio.sleep(0)
        center = (start_sec + end_sec) / 2
        window_start = max(0.0, center - 15.0)
        window_end = center + 15.0
        return [
            Candidate(
                start_sec=window_start,
                end_sec=window_end,
                score=None,
                source_ref="demo-fixture-expand",
                caption=f"Temporal expansion around {start_sec:.1f}–{end_sec:.1f} s (demo fixture)",
            )
        ]


class MockDetectionProvider:
    """Returns empty detections — no fabricated label claims."""

    async def detect(self, video_id: str, start_sec: float, end_sec: float) -> list[Detection]:
        await asyncio.sleep(0)
        return []


class MockReasoningProvider:
    """Returns a clearly labeled mock reasoning result."""

    async def reason(
        self,
        video_id: str,
        start_sec: float,
        end_sec: float,
        question: str,
        evidence: list[str],
    ) -> ReasoningResult:
        await asyncio.sleep(0)
        return ReasoningResult(
            summary="[Mock reasoning] No live model available. Retrieval evidence shown above.",
            supported=False,
            detail="Configure NVIDIA_API_KEY and a verified Cosmos endpoint to enable live reasoning.",
        )
