# SceneTrace — Architecture

## What the system does

A user types a natural-language near-miss query ("forklift approaching a pedestrian"). SceneTrace searches the VAST-indexed video archive semantically, returns ranked clips with timestamps and YOLO detection labels, lets the user load the exact moment in the video player, runs a structured near-miss investigation with Cosmos reasoning, and generates an evidence-backed safety report.

---

## What each component does

### VAST Data (VSS — Video Search Service)

The organizer deploys a VSS instance that holds a semantic index of warehouse footage. SceneTrace uses it as the search and streaming layer.

| What it does | VSS endpoint | SceneTrace code |
|---|---|---|
| Archive-wide semantic search — finds clips matching a query | `POST /api/v1/search` | `VastSearchProvider.search()` |
| Temporal expand — all segments of one video (before/during/after) | `GET /api/v1/tools/segments` | `VastSearchProvider.expand()` |
| Browse indexed clip archive — populates the video selector | `GET /api/v1/videos/explore` | `media.load_vss_videos()` |
| Stream video to the browser player | `GET /api/v1/videos/stream` | `VssClient.stream_proxy_request()` |
| Fetch YOLO class vocabulary for the filter dropdown | `GET /api/v1/metadata/values` | `main.list_object_classes()` |
| JWT authentication | `POST /api/v1/auth/login` | `VssClient.login()` |

### NVIDIA Cosmos (via VSS agent endpoint)

The VSS agent routes questions through a Cosmos-backed reasoning model. SceneTrace sends a structured near-miss analysis prompt that asks for observed behavior, hazardous interactions, contributing factors, consequences, and a preventive recommendation.

| What it does | VSS endpoint | SceneTrace code |
|---|---|---|
| Per-clip grounded near-miss reasoning | `POST /api/v1/agent/ask` | `CosmosReasoningProvider.reason()` |
| Combined retrieval + synthesis answer | `POST /api/v1/agent/search-and-answer` | `VastSearchProvider.grounded_answer()` |

The reasoning prompt explicitly forbids inventing timestamps, distances, speeds, or intentions not visible in footage.

### YOLO11 (precomputed detection sidecars)

At VSS ingest time, YOLO11 ran on every segment and stored bounding-box JSON as sidecars. SceneTrace reads these at query time to surface detected object labels (forklift, person, vehicle) on evidence cards.

| What it does | VSS endpoint | SceneTrace code |
|---|---|---|
| Per-segment YOLO11 detections | `GET /api/v1/videos/detections?source=` | `YoloDetectionProvider.detect()` |

### FastAPI backend (Python 3.12)

- Authenticates with VSS and caches the JWT token
- Routes queries through the deterministic investigation state machine
- Times out each provider independently; degrades gracefully
- Generates structured safety reports from session evidence
- Proxies video streams to the browser with byte-range support
- Runs in `mock` mode (fixture data) with no credentials required

Key endpoints:
- `POST /api/search` — archive-wide near-miss search
- `POST /api/investigate` — per-clip deep investigation
- `POST /api/report` — generate structured safety report
- `GET /api/videos/{id}/file` — streaming video proxy

### React frontend (Vite + TypeScript)

Single-page app with no routing library. Key flows:
1. **Archive search** — "Find Potential Near-Misses" box → result cards → click to load clip
2. **Investigation** — pre-filled query → evidence cards with YOLO labels and Cosmos reasoning
3. **Before/during/after** — "Investigate surrounding footage" button → temporal expand
4. **Report** — "Generate Safety Investigation Report" → six-section structured report

---

## Data flow: query to report

```
User types: "forklift approaching a pedestrian"
    │
    ▼ POST /api/search
FastAPI → VastSearchProvider.search(query, top_k=10)
        → POST /api/v1/search (VAST VSS)
        ← ranked segments with original_video, timestamps, captions
        → register each original_video in VideoRegistry (stable vss-{sha1} id)
        ← ArchiveSearchResponse {results: [{video_id, start_sec, end_sec, caption, location, camera_id}]}
    │
    ▼ User clicks result card → video player seeks to start_sec
    │
    ▼ POST /api/investigate {video_id: "vss-abc123", query: "..."}
FastAPI → VastSearchProvider.search(video_id, query, original_video=<URI>)
        → POST /api/v1/search scoped to this clip
        ← top candidates
        → YoloDetectionProvider.detect(source=<segment URI>)
        → GET /api/v1/videos/detections
        ← YOLO11 labels (forklift, person, …)
        → CosmosReasoningProvider.reason(start, end, question)
        → POST /api/v1/agent/ask with near-miss prompt
        ← structured analysis (observations, factors, recommendations)
        ← InvestigateResponse {events, tool_trace, warnings, session_id}
    │
    ▼ POST /api/report {session_id}
FastAPI → generate_report(session_id)
        pulls all session events from in-memory store
        builds six-section safety report (A–F)
        ← IncidentReport {sections, incidents, uncertainty_notes, source_references}
```

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

Swapping `mock` ↔ `live` is a single env var change (`SCENETRACE_MODE`). No code changes needed.

---

## Sponsor tool verification

| Tool | Integrated | How | What would break without it |
|---|---|---|---|
| VAST VSS | ✅ | 6 endpoints, JWT auth | No search, no video list, no streaming |
| NVIDIA Cosmos | ✅ via VSS agent | `agent/ask` + `search-and-answer` | No model-verified reasoning; retrieval still works |
| YOLO11 | ✅ via VSS sidecars | `videos/detections` | No object labels on evidence cards |
| W&B | ❌ not integrated | env var placeholder only | Nothing — not in the code path |

Note: Cosmos and YOLO are accessed through the VSS API, not raw NIM/YOLO endpoints. The organizer VSS backend runs them at ingest/query time.
