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
            f"Analyze first-person cyclist POV footage from {start_sec:.1f}s "
            f"to {end_sec:.1f}s. User query: {question}\\n"
            "Act as a proactive cycling safety investigator. "
            "Examine EVERY supplied segment for potential hazards, not just collisions. "
            "Treat the camera rider as the reference point. "
            "Look for cars, cyclists, pedestrians, parked vehicles, curbs, "
            "bollards, doors, barriers, and other obstacles approaching or passing "
            "apparently close to the rider. "
            "Prioritize narrowing gaps, converging paths, restricted clearance, "
            "sudden braking, swerving, and limited reaction opportunities. "
            "A close pass should be flagged as HAZARDOUS PROXIMITY for review, "
            "but not automatically described as a confirmed near-miss. "
            "Provide these labeled sections:\\n"
            "OBSERVED INTERACTION: Describe the objects and visible movements.\\n"
            "RISK CLASSIFICATION: Potential near-miss, hazardous proximity, "
            "routine activity, or insufficient evidence.\\n"
            "CONTRIBUTING FACTORS: Examine speed, reaction time, visibility, "
            "available space, passing clearance, and positioning. "
            "Emphasize how speed could increase risk or reduce reaction time, "
            "but do not claim speeding without supporting evidence.\\n"
            "ACCIDENT PREVENTION: Give 2-3 actionable recommendations. "
            "Discuss slowing down where appropriate, maintaining safe clearance, "
            "anticipating obstacles, and adjusting road position when safe. "
            "Explain how each recommendation addresses the observed situation.\\n"
            "UNCERTAINTY: State what the evidence cannot establish. "
            "Do not invent speeds, distances, collisions, traffic violations, "
            "intentions, or exact causes. "
            "If no close encounter is visible, give a routine-activity "
            "assessment and general preventive advice, not a fabricated incident. "
            "Use only the retrieved evidence and its supported timestamps."
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
