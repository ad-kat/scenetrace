# SceneTrace — Architecture

## System overview

```
Browser (React/Vite/TS)
    │  GET /api/videos
    │  POST /api/investigate
    │  POST /api/report
    │  GET /api/videos/{id}/file   (byte-range stream)
    ▼
FastAPI backend (Python 3.12)
    │
    ├─ VastSearchProvider ──────► POST /api/v1/search
    │                             GET  /api/v1/tools/segments
    │                             GET  /api/v1/videos/explore
    │                             GET  /api/v1/metadata/values
    │
    ├─ YoloDetectionProvider ───► GET  /api/v1/videos/detections?source=
    │
    ├─ CosmosReasoningProvider ─► POST /api/v1/agent/ask
    │                             POST /api/v1/agent/search-and-answer
    │
    └─ StreamProxy ─────────────► GET  /api/v1/videos/stream?source=&token=
```

All live calls go through `VssClient` (`backend/app/providers/vss_client.py`), which handles JWT login, token caching, auto-refresh on 401, and async streaming.

---

## Sponsor tool integrations

### 1. VAST Data — VSS (Video Search Service)

**What it does:** The organizer-deployed VSS instance holds a semantic index of warehouse footage. SceneTrace uses it as the primary evidence retrieval layer.

**Verified API endpoints used:**

| Endpoint | Used by | Purpose |
|---|---|---|
| `POST /api/v1/auth/login` | `VssClient.login()` | JWT authentication |
| `POST /api/v1/search` | `VastSearchProvider.search()` | Semantic similarity search over indexed segments |
| `GET /api/v1/tools/segments` | `VastSearchProvider.expand()` | Temporal expand: all segments of a video for before/during/after |
| `GET /api/v1/videos/explore` | `media.load_vss_videos()` | Browse indexed clip archive |
| `GET /api/v1/videos/stream` | `VssClient.stream_proxy_request()` | JWT-authenticated video stream proxied to browser |
| `GET /api/v1/metadata/values` | `/api/metadata/object-classes` endpoint | YOLO class vocabulary for the UI filter |

**Files:** `backend/app/providers/vss_client.py`, `backend/app/providers/vast.py`, `backend/app/media.py`

---

### 2. NVIDIA Cosmos — reasoning via VSS agent

**What it does:** The VSS agent endpoint routes questions through a Cosmos-backed reasoning model that answers grounded in indexed segment evidence.

**Verified API endpoints used:**

| Endpoint | Used by | Purpose |
|---|---|---|
| `POST /api/v1/agent/ask` | `CosmosReasoningProvider.reason()` | Per-clip grounded question answering |
| `POST /api/v1/agent/search-and-answer` | `VastSearchProvider.grounded_answer()` | Combined retrieval + synthesis |

The reasoning prompt is constrained: it references the specific time window and prior retrieval captions, and explicitly tells the model not to invent timestamps.

**Files:** `backend/app/providers/cosmos.py`

**Honest caveat:** SceneTrace does not call a Cosmos GPU/NIM endpoint directly — it uses the organizer VSS agent, which is backed by Cosmos. Whether the organizer counts this as "Cosmos usage" should be clarified.

---

### 3. YOLO11 — precomputed detection sidecars

**What it does:** The VSS ingestion pipeline ran YOLO11 on each segment at index time and stored detection sidecars. SceneTrace reads these at query time to surface detected object labels and bounding boxes.

**Verified API endpoint used:**

| Endpoint | Used by | Purpose |
|---|---|---|
| `GET /api/v1/videos/detections?source=` | `YoloDetectionProvider.detect()` | Per-segment YOLO11 bbox JSON |

The response shape handled: `frames[].detections[].{label, confidence, bbox}` with fallback to aggregate `object_classes` when frame-level data is absent.

**Files:** `backend/app/providers/yolo.py`

---

### W&B — NOT integrated

`WANDB_API_KEY` and `WANDB_MODEL` appear as env var placeholders in `.env.example` and `config.py` but no W&B SDK calls are made anywhere in the codebase. To integrate: the incident report generator (`backend/app/report.py`) could call a W&B-hosted inference endpoint to produce a richer narrative. This requires credentials and a confirmed endpoint URL.

---

## Investigation flow (agent.py)

```
InvestigateRequest
    │
    1. validate session + selected_event
    2a. if selected_event: search_provider.expand(video_id, start, end, query, window=15s)
    2b. else:             search_provider.search(video_id, query, top_k=5)
               + grounded_answer() [VAST/Cosmos, non-blocking]
    3. clip candidates to video duration; deduplicate overlapping windows
    4. detection_provider.detect() on top 3 candidates   [YOLO]
    5. reasoning_provider.reason() on top 2 candidates   [Cosmos]
    6. build Event objects with evidence, labels, location, camera_id
    7. store in session; build InvestigateResponse
```

All provider calls are independently time-bounded (`asyncio.wait_for`). A timed-out provider degrades gracefully: the investigation continues with whatever evidence was collected, and a warning is added to the response.

---

## Provider abstraction

```python
class SearchProvider(Protocol):
    async def search(video_id, query, top_k) -> list[Candidate]: ...
    async def expand(video_id, start_sec, end_sec, query) -> list[Candidate]: ...

class DetectionProvider(Protocol):
    async def detect(video_id, start_sec, end_sec) -> list[Detection]: ...

class ReasoningProvider(Protocol):
    async def reason(video_id, start_sec, end_sec, question, evidence) -> ReasoningResult: ...
```

`mock` mode replaces all three with deterministic fixture providers. `live` uses VAST/YOLO/Cosmos. `hybrid` combines both (demo video on mock, live for VSS-indexed clips).

---

## Session state

In-memory `SessionStore` (not durable across restart). Session IDs are UUIDs. Events are stored by `{session_id → {event_id → Event}}`. Follow-up queries reference an existing event by ID within the same session; cross-session references return HTTP 400.

---

## Deployment layout

```
backend/
  app/main.py          FastAPI app + endpoints
  app/agent.py         Investigation orchestrator
  app/providers/
    vss_client.py      Authenticated HTTP client
    vast.py            VAST search adapter
    cosmos.py          Cosmos reasoning adapter
    yolo.py            YOLO detection adapter
    mock.py            Deterministic fixture providers
  app/report.py        Incident report generator
  app/schemas.py       Pydantic contracts
  app/config.py        Settings (pydantic-settings)
  app/media.py         Video registry + VSS explore
  app/video_registry.py  stable_video_id, upsert, get
  app/fixtures.py      Demo fixture events
  static/              Built frontend (copied at deploy time)

frontend/
  src/App.tsx          Single-page app
  src/api.ts           Typed fetch wrappers
  src/types.ts         TypeScript contracts
  vite.config.ts       base='./' for /app path rewrite
```
