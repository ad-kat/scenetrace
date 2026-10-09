"""SceneTrace FastAPI application entry point."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import asyncio

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse, Response

from app.agent import run_investigation
from app.config import get_settings
from app.report import generate_report
from app.media import (
    ensure_video_known,
    get_video_list_async,
    is_valid_video_id,
    resolve_video_path,
)
from app.providers.base import ProviderNotConfigured
from app.providers.cosmos import CosmosReasoningProvider
from app.providers.mock import (
    MockDetectionProvider,
    MockReasoningProvider,
    MockSearchProvider,
)
from app.providers.vast import VastSearchProvider
from app.providers.vss_client import VssClient
from app.providers.yolo import YoloDetectionProvider
from app.fixtures import archive_lookup
from app.schemas import (
    ArchiveSearchRequest,
    ArchiveSearchResponse,
    ArchiveSearchResult,
    ErrorDetail,
    ErrorResponse,
    IncidentReport,
    IncidentReportRequest,
    InvestigateRequest,
    InvestigateResponse,
    ProviderMode,
    VideoInfo,
)
from app.video_registry import get_registry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def _lifespan(app: FastAPI):  # noqa: ARG001
    yield
    if _vss_client is not None:
        await _vss_client.aclose()


app = FastAPI(title="SceneTrace", version="0.2.0", lifespan=_lifespan)

_cors = (
    ["*"]
    if settings.scenetrace_mode in {"live", "hybrid"}
    else settings.cors_origins
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------

_vss_client: VssClient | None = None
_mock_search = MockSearchProvider()
_mock_detection = MockDetectionProvider()
_mock_reasoning = MockReasoningProvider()
_live_search: VastSearchProvider | None = None
_live_detection: YoloDetectionProvider | None = None
_live_reasoning: CosmosReasoningProvider | None = None
_mode = ProviderMode(settings.scenetrace_mode)


def _init_providers() -> None:
    global _vss_client, _live_search, _live_detection, _live_reasoning, _mode
    _mode = ProviderMode(settings.scenetrace_mode)
    if settings.scenetrace_mode == "mock":
        return

    if not settings.vss_configured:
        if settings.scenetrace_mode == "live":
            logger.error("Live mode requested but VSS credentials are not configured")
            _mode = ProviderMode.mock
        return

    try:
        _vss_client = VssClient(
            base_url=settings.resolved_vss_url,
            username=settings.resolved_vss_username,
            password=settings.resolved_vss_password,
            timeout=max(settings.search_timeout_seconds, 30.0),
        )
        _live_search = VastSearchProvider(_vss_client)
        _live_detection = YoloDetectionProvider(_vss_client)
        _live_reasoning = CosmosReasoningProvider(_vss_client)
        logger.info("VSS live providers initialized (mode=%s)", _mode.value)
    except ProviderNotConfigured as exc:
        logger.error("VSS provider init failed: %s", exc)
        _mode = ProviderMode.mock


def _providers_for_video(video_id: str):
    use_live = (
        _mode in {ProviderMode.live, ProviderMode.hybrid}
        and _live_search is not None
        and video_id.startswith("vss-")
    )
    if use_live:
        return _live_search, _live_detection, _live_reasoning, _mode
    # demo-01 and mock path
    mode = ProviderMode.mock if _mode == ProviderMode.mock else (
        ProviderMode.hybrid if _live_search else ProviderMode.mock
    )
    return _mock_search, _mock_detection, _mock_reasoning, mode


_init_providers()


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
            error=ErrorDetail(
                code="internal_error", message="An unexpected error occurred."
            )
        ).model_dump(),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "provider_mode": _mode.value,
        "vss_configured": settings.vss_configured,
    }


@app.get("/api/videos", response_model=list[VideoInfo])
async def list_videos() -> list[VideoInfo]:
    return await get_video_list_async(_vss_client)


@app.get("/api/metadata/object-classes")
async def list_object_classes() -> dict:
    if _vss_client is None:
        return {"field": "object_classes", "values": [], "count": 0}
    try:
        data = await _vss_client.metadata_values("object_classes", limit=80)
        values = data.get("values") or []
        return {
            "field": "object_classes",
            "values": values,
            "count": len(values),
        }
    except Exception as exc:
        logger.warning("object_classes metadata failed: %s", exc)
        return {"field": "object_classes", "values": [], "count": 0, "error": str(exc)}


@app.get("/api/videos/{video_id}/file")
async def get_video_file(video_id: str, request: Request) -> Response:
    # Demo local file
    if video_id == "demo-01":
        try:
            path = resolve_video_path(video_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="Video not found")
        if not path.exists():
            raise HTTPException(status_code=404, detail="Video file not on disk")
        return _serve_local_range(path, request)

    # Live VSS stream proxy (parent chunk preferred for timeline seeks)
    entry = get_registry().get(video_id)
    if entry is None or _vss_client is None:
        raise HTTPException(status_code=404, detail="Video not found")

    source = entry.original_video or entry.preview_source
    if not source:
        raise HTTPException(status_code=404, detail="No playable source for video")

    range_header = request.headers.get("range")
    try:
        upstream = await _vss_client.stream_proxy_request(
            source, range_header=range_header
        )
    except Exception as exc:
        logger.error("Stream proxy failed: %s", exc)
        raise HTTPException(status_code=502, detail="Upstream video stream failed")

    if upstream.status_code >= 400:
        await upstream.aclose()
        raise HTTPException(status_code=upstream.status_code, detail="Stream error")

    headers = {}
    for key in (
        "Content-Type",
        "Content-Length",
        "Content-Range",
        "Accept-Ranges",
    ):
        val = upstream.headers.get(key)
        if val:
            headers[key] = val
    if "Accept-Ranges" not in headers:
        headers["Accept-Ranges"] = "bytes"

    async def body_iter():
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()

    return StreamingResponse(
        body_iter(),
        status_code=upstream.status_code,
        headers=headers,
        media_type=headers.get("Content-Type", "video/mp4"),
    )


def _serve_local_range(path: Path, request: Request) -> Response:
    range_header = request.headers.get("range")
    file_size = path.stat().st_size

    if range_header:
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


@app.post("/api/search", response_model=ArchiveSearchResponse)
async def archive_search(req: ArchiveSearchRequest) -> ArchiveSearchResponse:
    """Archive-wide near-miss search. Does not require a pre-selected video_id."""
    warnings: list[str] = []
    results: list[ArchiveSearchResult] = []

    if _mode == ProviderMode.mock or _live_search is None:
        fixtures = archive_lookup(req.query)
        for i, f in enumerate(fixtures):
            # Stable mock video_id derived from fixture title
            from app.video_registry import stable_video_id
            mock_orig = f"mock://demo/{f.camera_id}/{f.location}"
            vid = stable_video_id(mock_orig)
            registry = get_registry()
            registry.upsert(
                original_video=mock_orig,
                title=f.video_title,
                location=f.location,
                camera_id=f.camera_id,
            )
            results.append(ArchiveSearchResult(
                video_id="demo-01",  # mock always points at demo video
                title=f.video_title,
                start_sec=f.start_sec,
                end_sec=f.end_sec,
                score=f.score,
                caption=f.caption,
                location=f.location,
                camera_id=f.camera_id,
                original_video=None,
                source="mock",
            ))
        warnings.append("Demo fixtures — archive search not live.")
        return ArchiveSearchResponse(
            query=req.query, results=results, mode=ProviderMode.mock, warnings=warnings
        )

    # Live path: VSS semantic search across entire archive (no original_video filter)
    try:
        candidates = await asyncio.wait_for(
            _live_search.search(
                video_id="",
                query=req.query,
                top_k=req.top_k,
                original_video=None,
                object_classes=req.object_classes,
            ),
            timeout=settings.search_timeout_seconds,
        )
    except asyncio.TimeoutError:
        warnings.append(f"Archive search timed out after {settings.search_timeout_seconds:.0f}s.")
        candidates = []
    except Exception as exc:
        logger.error("Archive search failed: %s", exc)
        warnings.append(f"Archive search error: {exc}")
        candidates = []

    registry = get_registry()
    for c in candidates:
        if not c.original_video:
            continue
        entry = registry.upsert(
            original_video=c.original_video,
            title=(
                c.extra.get("filename")
                or f"{c.extra.get('location') or 'Clip'} · {c.extra.get('camera_id') or c.original_video[-20:]}"
            ),
            location=c.extra.get("location"),
            camera_id=c.extra.get("camera_id"),
            filename=c.extra.get("filename"),
        )
        results.append(ArchiveSearchResult(
            video_id=entry.video_id,
            title=entry.title,
            start_sec=c.start_sec,
            end_sec=c.end_sec,
            score=c.score,
            caption=c.caption,
            location=entry.location,
            camera_id=entry.camera_id,
            original_video=c.original_video,
            source="vss",
        ))

    if not results:
        warnings.append("No matching clips found in the indexed archive for this query.")

    return ArchiveSearchResponse(
        query=req.query, results=results, mode=_mode, warnings=warnings
    )


@app.post("/api/investigate", response_model=InvestigateResponse)
async def investigate(req: InvestigateRequest) -> InvestigateResponse:
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query must not be blank")

    # Refresh explore cache lazily so first investigate on a listed id works.
    if req.video_id.startswith("vss-") and not ensure_video_known(req.video_id):
        if _vss_client is not None:
            await get_video_list_async(_vss_client)
        if not ensure_video_known(req.video_id):
            raise HTTPException(
                status_code=400, detail=f"Unknown video_id: {req.video_id!r}"
            )
    elif not is_valid_video_id(req.video_id) and not ensure_video_known(req.video_id):
        raise HTTPException(
            status_code=400, detail=f"Unknown video_id: {req.video_id!r}"
        )

    videos = {v.id: v for v in await get_video_list_async(_vss_client)}
    duration = videos[req.video_id].duration_sec if req.video_id in videos else None
    if duration is None:
        entry = get_registry().get(req.video_id)
        if entry:
            duration = entry.duration_sec

    search_p, det_p, reason_p, mode = _providers_for_video(req.video_id)
    try:
        return await run_investigation(
            req=req,
            search_provider=search_p,
            detection_provider=det_p,
            reasoning_provider=reason_p,
            mode=mode,
            video_duration=duration,
            search_timeout=settings.search_timeout_seconds,
            reasoning_timeout=settings.reasoning_timeout_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/report", response_model=IncidentReport)
async def create_report(req: IncidentReportRequest) -> IncidentReport:
    if not req.session_id.strip():
        raise HTTPException(status_code=400, detail="session_id must not be blank")
    try:
        return generate_report(req.session_id, title=req.title)
    except Exception as exc:
        logger.error("Report generation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Report generation failed")


# Serve built frontend (deploy / local preview) when present.
_STATIC_DIR = Path(__file__).resolve().parents[1] / "static"
if not _STATIC_DIR.exists():
    _STATIC_DIR = Path(__file__).resolve().parents[2] / "frontend" / "dist"

if _STATIC_DIR.exists():
    @app.get("/")
    async def spa_index() -> FileResponse:
        return FileResponse(_STATIC_DIR / "index.html")

    app.mount("/assets", StaticFiles(directory=_STATIC_DIR / "assets"), name="assets")
