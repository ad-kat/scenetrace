# SceneTrace — Friday PRD
**Event:** Real-Time Video Agents Hack, VAST Builders Challenge · Friday, October 9, 2026  
**Status:** Implementation specification v1.0 · **Owner:** two-person hackathon team  
**Working directory:** `~/scenetrace` on WSL2, shared GitHub repo with macOS teammate

## 1. Mission and product thesis
**SceneTrace is an evidence-grounded agent for investigating recorded video.** A user selects a permitted video, asks in natural language what happened, gets ranked events with exact start/end timestamps and playable footage, then asks a context-sensitive follow-up such as “what happened before event 2?” Its distinguishing behavior is **search → inspect → verify → explain with evidence**, not merely searching for semantically similar clips.

### User promise
“Find the moment, show me the proof, and help me investigate what happened around it.”

### Personas and jobs to be done
- Operations analyst reviewing permitted warehouse/industrial footage: locate incidents or object interactions and identify temporal context.
- Video archivist/researcher: retrieve moments buried in long footage without manual scrubbing.
- Event reviewer: revisit precise moments, inspect detections, and ask follow-up questions.

### Explicit boundaries
This MVP is for **consented or legally permitted demo videos**, not covert surveillance or definitive identity matching. No face identification, biometric recognition, or unsupported accusation of wrongdoing. Persons/objects may use track-local pseudonymous IDs only when tracking actually supports them.

## 2. User journeys and acceptance criteria
**UJ1 — choose footage:** User can pick a bundled demo video from a visible list; its title, length, and playback are available. Uploading a local MP4 up to a configurable safe size is optional, never a prerequisite for a working demo.

**UJ2 — investigate:** Given `video_id` and a plain-English query, SceneTrace returns 0–5 relevant events, each with `start_sec`, `end_sec`, `explanation`, `evidence`, `source`, `status`, and a *playable* corresponding video segment or seek action. Empty results show “No supported evidence found,” never fabricated timestamps.

**UJ3 — inspect:** Clicking “Jump to moment” seeks within the video player and highlights the event on a timeline. Timestamps must remain in range and map to the served source video.

**UJ4 — follow up:** User asks “What happened just before this?” while an event is selected. Agent expands a bounded time window (default 15 seconds before/after, clipped to duration) and produces a fresh evidence-backed result for the **same video**. Unsupported content is disclosed.

**UJ5 — optional object detection:** If a usable YOLO service or local compatible model is provided, overlays boxes or lists detected labels for candidate clips. Missing tracking does NOT imply the same person across scenes.

**UJ6 — resilience:** UI can run in a clearly labeled **demo/mock mode** with deterministic fixtures and a local demo video. No external sponsor credentials are required for boot, `GET /health`, sample investigation, or UI playback. Never label mock output as real model findings.

## 3. Priorities
| Priority | Feature | Done when |
|---|---|---|
| P0 | React/Vite/TS app + video playback | Demo video plays and seeking works |
| P0 | FastAPI service + typed contract | `/health`, `/api/videos`, `/api/investigate` work |
| P0 | Pluggable search provider | Mock works; real adapter is isolated/configurable |
| P0 | Evidence cards + timestamp timeline | User navigates from response to real source footage |
| P0 | Query/session event context | Follow-up references an event safely |
| P0 | Tests + docs + demo | Both WSL2 and macOS startup instructions validated |
| P1 | Cosmos reasoning over candidate window | Model finding tied to clip reference, no invented API |
| P1 | YOLO detection evidence | UI displays only actual detections |
| P1 | Structured trace of which tools ran | Shows search/detect/reason steps and failures |
| P2 | Optional upload, multiple videos, tracking | Only after P0/P1 stable |

## 4. Design requirements
Single responsive screen with: project name and source status, demo video selector, video player, query input, investigation progress indicator, 0–5 evidence cards, clickable timestamps, optional tool trace, and graceful errors. Useful keyboard and accessible labels. Do not spend time on auth, billing, user profiles, full analytics, themes or excessive visual effects.

## 5. Success metrics and judging story
- Live demo: from question to seekable evidence in 3 actions or fewer.
- Zero fabricated event timestamp or claim. Source clip/time always visible.
- 5 deterministic demo questions produce expected moments using fixtures; at least one follow-up succeeds.
- Real-provider benchmark (when available): report *measured* p50/median response time and retrieved evidence relevance across 5 hand-labeled queries; do not invent accuracy.
- Pitch emphasizes **product usefulness**, **compositional technical design**, and **auditability**.

## 6. Non-goals
No model training, arbitrary CCTV surveillance platform, biometric re-identification, autonomous external actions, full production deployment, ingestion of terabytes, video at unrestricted FPS, enterprise authentication, or guaranteed real-time SLAs.

## 7. Sponsor dependency rules
Organizers advertise NVIDIA Cosmos (video understanding), semantic search, YOLO, W&B models, VAST AI OS, and CoreWeave GPUs. **Exact endpoints, permissions, SDKs, available models, schemas, quotas and whether footage is already indexed are UNKNOWN until onboarding.** Implement provider boundaries, not guessed network requests. The mock/local happy path must always remain functional. Record each discovered actual API in `docs/INTEGRATION_NOTES.md`.

## 8. Definition of done
A clean checkout can run backend + frontend from README, use a committed/legal fixture video or a deterministic generated test video, ask and follow up on a question, click a timestamp to seek, pass tests and lint/build, and distinguish real vs simulated evidence. Publish screenshots and a brief demo script.
