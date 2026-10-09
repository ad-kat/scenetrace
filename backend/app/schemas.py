"""Shared Pydantic schemas for the SceneTrace API contract."""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class VerificationStatus(str, Enum):
    verified_model = "verified_model"
    retrieval_only = "retrieval_only"
    unverified_mock = "unverified_mock"


class ProviderMode(str, Enum):
    mock = "mock"
    live = "live"
    hybrid = "hybrid"


# ---------------------------------------------------------------------------
# Video registry
# ---------------------------------------------------------------------------

class VideoInfo(BaseModel):
    id: str
    title: str
    duration_sec: float | None = None
    video_url: str
    source: str = "demo"


# ---------------------------------------------------------------------------
# Investigation request / response
# ---------------------------------------------------------------------------

class InvestigateRequest(BaseModel):
    video_id: str = Field(..., min_length=1)
    query: str = Field(..., min_length=1, max_length=500)
    selected_event_id: str | None = None
    session_id: str | None = None


class EvidenceItem(BaseModel):
    kind: str  # "retrieval" | "detection" | "reasoning"
    detail: str
    start_sec: float | None = None
    end_sec: float | None = None


class Event(BaseModel):
    event_id: str
    video_id: str
    start_sec: float
    end_sec: float
    explanation: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    score: float | None = None
    verification: VerificationStatus = VerificationStatus.unverified_mock

    @model_validator(mode="after")
    def _validate_times(self) -> "Event":
        if self.start_sec < 0 or self.end_sec < 0:
            raise ValueError("start_sec and end_sec must be non-negative")
        if self.start_sec >= self.end_sec:
            raise ValueError("start_sec must be less than end_sec")
        return self


class ToolTraceEntry(BaseModel):
    tool: str
    status: str
    duration_ms: int
    detail: str | None = None


class InvestigateResponse(BaseModel):
    session_id: str
    mode: ProviderMode
    answer: str
    events: list[Event] = Field(default_factory=list)
    tool_trace: list[ToolTraceEntry] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Error envelope
# ---------------------------------------------------------------------------

class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
