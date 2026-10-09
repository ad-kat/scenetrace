"""SceneTrace FastAPI application entry point."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import FileResponse, Response

from app.agent import run_investigation
from app.config import get_settings
from app.media import get_video_list, is_valid_video_id, resolve_video_path
from app.providers.mock import (
    MockDetectionProvider,
    MockReasoningProvider,
    MockSearchProvider,
)
from app.schemas import (
    ErrorDetail,
    ErrorResponse,
    InvestigateRequest,
    InvestigateResponse,
    ProviderMode,
    VideoInfo,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="SceneTrace", version="0.1.0")

settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------

_search = MockSearchProvider()
_detection = MockDetectionProvider()
_reasoning = MockReasoningProvider()
_mode = ProviderMode(settings.scenetrace_mode)


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content=ErrorResponse(
            error=ErrorDetail(code="validation_error", message=str(exc))
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled error: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error=ErrorDetail(code="internal_error", message="An unexpected error occurred.")
        ).model_dump(),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "provider_mode": _mode.value}


@app.get("/api/videos", response_model=list[VideoInfo])
async def list_videos() -> list[VideoInfo]:
    return get_video_list()


@app.get("/api/videos/{video_id}/file")
async def get_video_file(video_id: str, request: Request) -> Response:
    if not is_valid_video_id(video_id):
        raise HTTPException(status_code=404, detail="Video not found")

    try:
        path = resolve_video_path(video_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Video not found")

    if not path.exists():
        raise HTTPException(status_code=404, detail="Video file not on disk")

    range_header = request.headers.get("range")
    file_size = path.stat().st_size

    if range_header:
        # Parse "bytes=start-end"
        try:
            byte_range = range_header.replace("bytes=", "")
            parts = byte_range.split("-")
            start = int(parts[0]) if parts[0] else 0
            end = int(parts[1]) if len(parts) > 1 and parts[1] else file_size - 1
        except (ValueError, IndexError):
            raise HTTPException(status_code=416, detail="Invalid range")

        if start > end or end >= file_size:
            raise HTTPException(status_code=416, detail="Range out of bounds")

        length = end - start + 1
        with open(path, "rb") as f:
            f.seek(start)
            data = f.read(length)

        return Response(
            content=data,
            status_code=206,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(length),
                "Content-Type": "video/mp4",
            },
        )

    return FileResponse(
        path=str(path),
        media_type="video/mp4",
        headers={"Accept-Ranges": "bytes"},
    )


@app.post("/api/investigate", response_model=InvestigateResponse)
async def investigate(req: InvestigateRequest) -> InvestigateResponse:
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query must not be blank")

    if not is_valid_video_id(req.video_id):
        raise HTTPException(
            status_code=400,
            detail=f"Unknown video_id: {req.video_id!r}",
        )

    videos = {v.id: v for v in get_video_list()}
    duration = videos[req.video_id].duration_sec if req.video_id in videos else None

    try:
        return await run_investigation(
            req=req,
            search_provider=_search,
            detection_provider=_detection,
            reasoning_provider=_reasoning,
            mode=_mode,
            video_duration=duration,
            search_timeout=settings.search_timeout_seconds,
            reasoning_timeout=settings.reasoning_timeout_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
