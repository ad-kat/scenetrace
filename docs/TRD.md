# SceneTrace — Friday Technical Requirements & Design (TRD)
**Implementation goal:** Build all code in `~/scenetrace` locally; share with teammate on macOS. The Python virtual environment is **`backend/tracenv`**. Treat this document as authoritative together with `PRD.md` and `WORKFLOW.md`.

## 1. Repository and cross-platform contract
```
scenetrace/
  README.md  .env.example  .gitignore  .gitattributes
  docs/PRD.md  docs/TRD.md  docs/WORKFLOW.md  docs/INTEGRATION_NOTES.md  docs/DEMO.md
  backend/
    requirements.txt  tests/
    app/main.py  app/config.py  app/schemas.py  app/agent.py
    app/providers/base.py  app/providers/mock.py
    app/providers/vast.py  app/providers/cosmos.py  app/providers/yolo.py
    app/media.py  app/fixtures.py
  frontend/
    package.json  src/App.tsx  src/api.ts  src/types.ts  src/components/
    public/sample.mp4 (only if legally distributable; otherwise local ignored media)
```
Respect existing scaffolding; do not destroy Vite config, user files, git history, or existing code. Use **Python 3.12**, **Node 20**, FastAPI, `httpx`, `pytest`, React + Vite + TypeScript, and built-in HTML video. Prefer **no database**, no Docker requirement and no model downloads. Lock npm dependencies via `package-lock.json`, pin practical Python major/minor dependency ranges. Use POSIX paths via `pathlib` and LF line endings. `.gitignore` must exclude `backend/tracenv`, `.env*` except `.env.example`, files/videos over appropriate size, Python cache and `node_modules`. NEVER commit secrets or private event-provided videos.

## 2. Exact shared API contract
`GET /health` → `{"status":"ok","provider_mode":"mock|live|hybrid"}`.

`GET /api/videos` → `[{"id":"demo-01","title":"Demo footage","duration_sec":120.0,"video_url":"/api/videos/demo-01/file","source":"demo"}]`. Duration must reflect actual media if available. Do not claim a duration unless known; schema may make it nullable.

`GET /api/videos/{video_id}/file` → supports byte-range requests (`206 Partial Content`) for browser seek. Use framework file streaming with correct Content-Type and range behavior, or serve immutable static assets via Vite/public. Only allow whitelisted video IDs, never arbitrary filesystem paths.

`POST /api/investigate` request:
```json
{"video_id":"demo-01","query":"Find when someone sets down a box","selected_event_id":null,"session_id":null}
```
Response (example **illustrative and not a real inference**):
```json
{
 "session_id":"session-001","mode":"mock","answer":"One candidate moment was located.",
 "events":[{"event_id":"evt-1","video_id":"demo-01","start_sec":12.0,"end_sec":19.5,
 "explanation":"An object is placed on a surface.","evidence":[{"kind":"retrieval","detail":"Matching annotated demo segment","start_sec":12.0,"end_sec":19.5}],
 "labels":["box"],"score":null,"verification":"unverified_mock"}],
 "tool_trace":[{"tool":"search","status":"ok","duration_ms":12}],"warnings":["Demo fixtures, not live inference"]
}
```
Validation: nonblank query max 500 chars, valid video IDs, finite nonnegative times, start < end, clip times <= known duration; selected event must belong to same session + video or return HTTP 400. If confidence/score unavailable use `null`, do not fabricate. Explicit mode and verification enums (`verified_model`, `retrieval_only`, `unverified_mock`). Error envelope: `{"error":{"code":"...","message":"..."}}`; appropriate 4xx for validation, 503 for unavailable required provider.

## 3. Agent orchestration
Implement a deterministic orchestration state machine, *not* an uncontrolled recursive LLM loop:
1. Validate query, video, session and selected event.
2. Interpret follow-up reference by session-scoped event ID, **not** by hallucinated cross-session memory.
3. Call `SearchProvider.search(video_id, query, top_k=5)` for initial search or `SearchProvider.expand(video_id,start,end,query)` for temporal follow-up.
4. Normalize provider results to `Candidate(start_sec,end_sec,score?,source_ref?,caption?)`; reject out-of-range or invalid windows; deduplicate overlaps.
5. If configured and needed, run `DetectionProvider.detect(video_id,start,end)` on 1–3 candidates.
6. If configured, run `ReasoningProvider.reason(video_id,start,end,question,evidence)` on candidate windows.
7. Construct evidence-backed answer; do not produce visually specific assertions unsupported by retrieval/detections/reasoning. If no hits, return empty list and clear explanation.
8. Record structured tool trace and typed warnings. Timeout independently per provider and degrade search-only where possible.
Default bounded windows: 15 seconds before/after for follow-up. IDs may be UUIDs, with in-memory session store, and must not be assumed durable across restart.

## 4. Provider interfaces
Create Python `Protocol`/ABC types with async functions:
- `SearchProvider.search(video_id, query, top_k) -> list[Candidate]`
- `SearchProvider.expand(video_id, start_sec, end_sec, query) -> list[Candidate]`
- `DetectionProvider.detect(video_id, start_sec, end_sec) -> list[Detection]`
- `ReasoningProvider.reason(video_id, start_sec, end_sec, question, evidence) -> ReasoningResult`
- Optional `LanguageModelProvider` only if actually needed for grounded synthesis.
Mock providers: deterministic fixtures keyed by sample query patterns; transparent simulation label. Live provider adapters: validate env/SDK and raise `ProviderNotConfigured` when absent. **Never invent VAST, CoreWeave, Cosmos, YOLO or W&B endpoint schemas.** Populate adapters only from verified organizer SDK/code/OpenAPI after event onboarding. Comment documented source/version beside real integrations. Sponsor access may be event-limited.

## 5. Video processing and client
Use `ffprobe` to probe duration where possible, `ffmpeg` for optional thumbnail/frame extraction and sample-video generation. Avoid local GPU requirements. Use bounded subprocess execution with `subprocess.run([...],shell=False,timeout=...)`; reject non-whitelisted media paths. Frontend: `HTMLVideoElement.currentTime = event.start_sec`; await metadata if required; browser-accessible URL from backend or public assets; handle CORS (`localhost:5173` only in dev) and loading errors. Display evidence and source quality, not fake percentages. Cache/reuse initialized provider clients; avoid expensive initialization on each request.

## 6. Environment configuration
`.env.example`:
```
SCENETRACE_MODE=mock
SCENETRACE_MEDIA_DIR=./media
SCENETRACE_CORS_ORIGINS=http://localhost:5173
VAST_API_URL=
VAST_API_KEY=
NVIDIA_API_KEY=
WANDB_API_KEY=
WANDB_MODEL=
SEARCH_TIMEOUT_SECONDS=15
REASONING_TIMEOUT_SECONDS=25
```
These are **application-owned placeholders**, not a claim about sponsor-required variable names. Never ship a secret to the browser. Preserve the ability to run mock mode with no keys.

## 7. Testing and verification
Backend `pytest` with tests for health, demo video list, investigation response schema, query validation, no-hits, bad event IDs, timestamp clipping, session isolation, search timeout fallback, and no leaked secret in logs. Fixture test video MUST have timestamp-known annotations; use a deterministic ffmpeg-generated video if redistribution rights are uncertain. Frontend `npm run build` and lint; test seeking, empty state, and selected-event follow-up (lightweight tests if time permits). Smoke: `curl localhost:8000/health`, POST investigate, play, click seek. Test on WSL2 Chrome/Edge and teammate macOS browser.

## 8. Observability, privacy, safety
Structured logs with session IDs, provider name, duration, failures; scrub credentials/media contents; avoid storing prompts containing personal info beyond ephemeral session state. Accessible tool trace for demo. Do not make identity, criminal, or sensitive-person inferences. Explicit fallback and mock-state UI banner.

## 9. Integration notes / authoritative docs
When credentials arrive, record exact endpoint, auth, response schema, token limits, permitted sample media, indexing readiness, rate limits and model naming. Useful background: https://docs.nvidia.com/cosmos/ ; these docs are **not** proof of which Cosmos endpoints the hackathon enables. Integrate event SDK first and leave everything else mocked if uncertain.
