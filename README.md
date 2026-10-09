# SceneTrace — Warehouse Safety Video Investigation Agent

**VAST Builders Challenge · Real-Time Video Agents Hack · Team 34**  
Deployment: `https://team-34-vss.thecosmoslabs.com/app`

SceneTrace is an evidence-grounded agent for investigating recorded warehouse footage. Ask a natural-language question, get ranked candidate incidents with exact timestamps, jump to the moment in the video, follow up on surrounding footage, and generate a structured incident report.

---

## Sponsor tools integrated

| Tool | How it is used | Code |
|---|---|---|
| **VAST VSS** | Semantic video search, clip streaming, segment inventory, explore, metadata values | `backend/app/providers/vss_client.py`, `backend/app/providers/vast.py` |
| **NVIDIA Cosmos** | Evidence-grounded reasoning over candidate clips via VSS agent endpoint | `backend/app/providers/cosmos.py` |
| **YOLO11** | Precomputed object-detection sidecars per segment, pulled at query time | `backend/app/providers/yolo.py` |
| W&B | Not integrated — env var placeholder only (`WANDB_API_KEY`, `WANDB_MODEL`) | `backend/app/config.py` |

---

## Quick start (local / WSL2 / macOS)

### Prerequisites
- Python 3.12, Node ≥ 20, ffmpeg

### 1. Generate demo video (first time only)

```bash
cd backend
python3 -m venv tracenv
source tracenv/bin/activate        # Windows: tracenv\Scripts\activate
pip install -r requirements.txt
mkdir -p ../media
python scripts/generate_demo_video.py
```

Or generate manually:

```bash
ffmpeg -y -f lavfi \
  -i "color=c=0x1a1a2e:size=1280x720:duration=120:rate=15,drawtext=fontcolor=white:fontsize=48:x=(w-tw)/2:y=(h-th)/2:text='SceneTrace Demo'" \
  -c:v libx264 -preset ultrafast -crf 28 -an ../media/demo-01.mp4
```

### 2. Start backend

```bash
# From backend/
cp ../.env.example ../.env       # first time; edit as needed
source tracenv/bin/activate
SCENETRACE_MEDIA_DIR=../media uvicorn app.main:app --reload --port 8000
```

### 3. Start frontend

```bash
# From frontend/
npm install
npm run dev      # dev server at http://localhost:5173
```

### 4. Run tests

```bash
cd backend
source tracenv/bin/activate
SCENETRACE_MEDIA_DIR=../media pytest -v
# Expected: 22 passed
```

### 5. Verify (smoke test)

```bash
curl -fsS http://localhost:8000/health
# → {"status":"ok","provider_mode":"mock","vss_configured":false}

curl -fsS -X POST http://localhost:8000/api/investigate \
  -H "Content-Type: application/json" \
  -d '{"video_id":"demo-01","query":"forklift near a worker"}'
# → events at 33s and 78s with labels ["forklift","person"]

curl -fsS -X POST http://localhost:8000/api/report \
  -H "Content-Type: application/json" \
  -d '{"session_id":"<session_id from above>"}'
# → structured incident report with sections, uncertainty notes, source references
```

---

## Configuration

Copy `.env.example` to `.env` and set values. Live mode requires VSS credentials.

| Variable | Default | Description |
|---|---|---|
| `SCENETRACE_MODE` | `mock` | `mock` \| `live` \| `hybrid` |
| `SCENETRACE_MEDIA_DIR` | `./media` | Path to demo video directory |
| `SCENETRACE_CORS_ORIGINS` | `http://localhost:5173` | Allowed origins (comma-separated) |
| `VSS_URL` | _(empty)_ | VSS base URL, e.g. `https://team-34-vss.thecosmoslabs.com` |
| `VSS_USERNAME` | _(empty)_ | VSS login username |
| `VSS_PASSWORD` | _(empty)_ | VSS login password |
| `SEARCH_TIMEOUT_SECONDS` | `30` | Per-provider search timeout |
| `REASONING_TIMEOUT_SECONDS` | `45` | Per-provider reasoning timeout |
| `EXPLORE_LIMIT` | `48` | Max clips returned from `/api/v1/videos/explore` |

The backend also reads organizer-injected secrets `INGRESS_URL`, `USERNAME`, `PASSWORD` as fallbacks for `VSS_URL`, `VSS_USERNAME`, `VSS_PASSWORD`.

### Live mode

```bash
SCENETRACE_MODE=live
VSS_URL=https://team-34-vss.thecosmoslabs.com
VSS_USERNAME=<provided>
VSS_PASSWORD=<provided>
```

---

## API reference

### `GET /health`
```json
{"status":"ok","provider_mode":"mock","vss_configured":false}
```

### `GET /api/videos`
Returns list of `VideoInfo` objects. In live/hybrid mode includes indexed VSS clips with location, camera_id, and original_video URI.

### `GET /api/videos/{video_id}/file`
Byte-range streaming proxy (supports browser `<video>` seeking). Demo videos served from local disk; VSS clips proxied through the JWT-authenticated stream endpoint.

### `POST /api/investigate`

**Input:**
```json
{
  "video_id": "demo-01",
  "query": "forklift near a worker in aisle 3",
  "selected_event_id": null,
  "session_id": null,
  "object_classes": ["forklift"],
  "metadata_filters": null
}
```

**Output:**
```json
{
  "session_id": "uuid",
  "mode": "mock",
  "answer": "Found 2 candidate moment(s) for: \"forklift near a worker\".",
  "events": [
    {
      "event_id": "uuid",
      "video_id": "demo-01",
      "start_sec": 33.0,
      "end_sec": 42.0,
      "explanation": "A forklift is operating in close proximity to a worker in the aisle.",
      "evidence": [{"kind":"retrieval","detail":"...","start_sec":33.0,"end_sec":42.0}],
      "labels": ["forklift","person"],
      "score": null,
      "verification": "unverified_mock",
      "location": null,
      "camera_id": null
    }
  ],
  "tool_trace": [{"tool":"search","status":"ok","duration_ms":1}],
  "warnings": ["Demo fixtures — not live inference. Results are illustrative only."],
  "timeline": [{"turn_id":"uuid","query":"...","event_ids":["uuid"],"answer_preview":""}]
}
```

Validation: query 1–500 chars, video_id must be known, selected_event_id must belong to current session (HTTP 400 otherwise).

### `POST /api/report`

**Input:**
```json
{"session_id": "uuid", "title": "Aisle 3 Forklift Incident — 2026-10-09"}
```

**Output:** `IncidentReport` with sections: Investigation Queries, Identified Incidents, Source Video References, Uncertainty and Limitations, Report Metadata.

---

## Architecture

```
User query
    │
    ▼
FastAPI /api/investigate
    │
    ├─► VastSearchProvider.search()
    │       POST /api/v1/search  →  ranked segment candidates
    │       (fallback: GET /api/v1/tools/segments)
    │
    ├─► YoloDetectionProvider.detect()
    │       GET /api/v1/videos/detections?source=  →  YOLO11 bbox JSON
    │
    ├─► CosmosReasoningProvider.reason()
    │       POST /api/v1/agent/ask  →  Cosmos-grounded answer
    │
    └─► build_events()  →  InvestigateResponse
            session_id, events[], tool_trace[], warnings[]
```

See `docs/ARCHITECTURE.md` for full detail.

---

## Deployment (from VAST VM)

```bash
# 1. Build frontend
cd frontend && npm ci && npm run build && cd ..

# 2. Copy dist to backend/static
mkdir -p backend/static
cp -r frontend/dist/* backend/static/

# 3. Set env
cp .env.example .env
# Edit: SCENETRACE_MODE=live, VSS_URL=..., VSS_USERNAME=..., VSS_PASSWORD=...

# 4. Install and run
cd backend
python3 -m venv tracenv && source tracenv/bin/activate
pip install -r requirements.txt
SCENETRACE_MEDIA_DIR=../media uvicorn app.main:app --host 0.0.0.0 --port 8000

# Then use the organizer deploy-app-no-registry skill.
```

The Vite build uses `base: './'` so all asset URLs work behind the `/app` path rewrite.

---

## Demo queries (mock mode)

| Query | Expected events |
|---|---|
| `forklift near a worker` | 33 s, 78 s (forklift + person labels) |
| `person walking` | 5 s, 65 s |
| `Find when someone sets down a box` | 12 s, 47 s |
| `door opening` | 30 s |
| `vehicle passing` | 88 s |
| `safety incident` | 33 s |
