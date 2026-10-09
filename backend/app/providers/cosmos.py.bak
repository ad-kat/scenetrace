"""Cosmos / VSS reasoning adapter.

Uses the retrieval agent — not raw GPU NIM URLs — so answers stay grounded in
indexed evidence (retrieval/agent-qa skill):
  POST /api/v1/agent/ask
"""
from __future__ import annotations

import logging

from app.providers.base import ReasoningResult
from app.providers.vss_client import VssClient

logger = logging.getLogger(__name__)


class CosmosReasoningProvider:
    def __init__(self, client: VssClient) -> None:
        self._client = client
        self._pending_original_video: str | None = None

    def set_original_video(self, original_video: str | None) -> None:
        self._pending_original_video = original_video

    async def reason(
        self,
        video_id: str,
        start_sec: float,
        end_sec: float,
        question: str,
        evidence: list[str],
    ) -> ReasoningResult:
        original = self._pending_original_video
        window_q = (
            f"Analyze the segment from {start_sec:.1f}s to {end_sec:.1f}s for "
            f"potential near-miss safety events. Question: {question}\n"
            "Describe: (A) what objects and people are visibly doing, "
            "(B) any potential near-miss or hazardous interaction, "
            "(C) possible contributing factors such as shared pathways or obstructed sightlines, "
            "(D) possible consequences if the situation worsened, "
            "(E) one preventive recommendation. "
            "Use language like 'potential contributing factor' and 'requires human verification'. "
            "Do not claim verified distances, speeds, intentions, or causes not visible in the footage. "
            "Only use indexed segment evidence; do not invent timestamps."
        )
        if evidence:
            window_q += " Prior retrieval captions: " + " | ".join(evidence[:3])

        try:
            body: dict = {"question": window_q, "top_k": 5}
            if original:
                body["original_video"] = original
            data = await self._client.agent_ask(body)
            answer = (data.get("answer") or "").strip()
            if not answer:
                return ReasoningResult(
                    summary="",
                    supported=False,
                    detail="Agent returned an empty answer.",
                )
            return ReasoningResult(
                summary=answer,
                supported=True,
                detail=f"tool_used={data.get('tool_used')}",
            )
        except Exception as exc:
            logger.warning("VSS agent reasoning failed: %s", exc)
            return ReasoningResult(
                summary="",
                supported=False,
                detail=str(exc),
            )
