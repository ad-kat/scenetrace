# SceneTrace — 2-Minute Demo Walkthrough

**Event:** VAST Builders Challenge · Real-Time Video Agents Hack · Team 34  
**Deployment:** https://team-34-vss.thecosmoslabs.com/app

---

## Pre-demo checklist

- [ ] Backend running: `curl -fsS http://localhost:8000/health` returns `"status":"ok"`
- [ ] Frontend open: http://localhost:5173 (dev) or deployment URL
- [ ] In live mode: `provider_mode` shows `live` or `hybrid` in the top badge
- [ ] In mock mode: badge reads "DEMO MODE" — tell the audience before starting
- [ ] Have `session_id` from a prior run ready as backup (see backup plan)

---

## 2-Minute Script

### 0:00 — Open and orient (15 s)
*"This is SceneTrace — a warehouse safety investigation agent. It takes a natural-language question, searches indexed video for evidence, and gives you timestamped moments you can immediately jump to. No manual scrubbing."*

Point to the header badge: live vs. mock mode clearly labeled.

### 0:15 — Select footage (10 s)
Select the first video from the dropdown. In live mode this shows clips from the VAST-indexed archive with location and camera ID. The browser video player loads.

### 0:25 — Run a safety investigation query (20 s)
Type: **`forklift near a worker in the aisle`**  
Click **Investigate**.

*"We're hitting the VAST VSS semantic search API right now — it embeds the query and retrieves the closest indexed segments."*

Point to the loading indicator while it runs.

### 0:45 — Evidence cards (25 s)
Two cards appear: **33 s–42 s** and **78 s–86 s**, both labeled `forklift + person`.

*"Each card has a precise timestamp, detected object labels from YOLO11, and a verification badge. In live mode you'll also see the warehouse location and camera ID on the card."*

Click the **33 s** timestamp. The video seeks immediately.  
Point to the timeline marker on the scrubber.

### 1:10 — Follow up — before/during/after (20 s)
Click **Follow up** on the first card.

*"This expands a 15-second window around the event — we get the context before, during, and after the incident — all grounded in retrieved evidence, not hallucinated."*

The Investigation Timeline section appears showing Turn 1 → Turn 2, with the follow-up relationship visible.

### 1:30 — Generate incident report (20 s)
Click **Generate incident report**.

*"The report pulls every event from this session with source references, uncertainty notes, and a structured narrative — ready to hand to a safety officer or export."*

Expand the "Identified Incidents" section. Show timestamped entries with location/camera.

### 1:50 — Tool trace + close (10 s)
Expand the **Tool trace** panel under results.

*"Every call — search, detection, reasoning — is logged with its tool, status, and latency. When Cosmos reasoning runs, its entry appears here. Zero black boxes."*

*"VAST search. YOLO detections. Cosmos reasoning. Evidence you can audit."*

---

## Demo queries (in order of impact)

| Query | Audience moment |
|---|---|
| `forklift near a worker in the aisle` | Primary — safety incident |
| `What happened just before this?` (follow-up) | Before/during/after timeline |
| `person walking near hazard zone` | Second search query |
| `door opening into a travel path` | Tertiary |

---

## Backup demonstration plan

### If live VSS is unavailable
The app boots in **mock mode** automatically — no credentials needed.
1. Set `SCENETRACE_MODE=mock` in `.env`
2. Restart backend; top badge reads "DEMO MODE"
3. All five demo queries return deterministic fixture events with real timestamps
4. All UI flows work identically — event cards, jump-to-moment, follow-up, report

Tell the judges: *"We're in demo/mock mode — the VAST live integration code is all there, the provider is swapped out; the workflow is identical."*

### If video streaming fails (VSS proxy issue)
The video player shows an error overlay. The investigation flow still works:
- Event cards, timestamps, follow-up, and report are all text-based
- Demonstrate by showing the evidence cards and tool trace without playback

### If report endpoint is slow
The backend generates reports synchronously from in-memory session state — it's instant. No fallback needed.

### Offline fallback
Pre-run an investigation locally and screenshot the results. Show the JSON from:
```bash
curl -fsS -X POST http://localhost:8000/api/investigate \
  -H "Content-Type: application/json" \
  -d '{"video_id":"demo-01","query":"forklift near a worker"}'
```

---

## Technical talking points for judges

**Idea:** Warehouse safety review is a real, underserved use case. Investigators currently scrub footage manually. SceneTrace turns that into a structured query-evidence-report workflow.

**Technical implementation:**
- Provider-independent orchestration: swap mock ↔ live by changing one env var
- VAST VSS client with JWT auth and token refresh, matching verified API contracts
- Temporal expand for before/during/after: uses `/api/v1/tools/segments` inventory
- YOLO11 detection sidecars pulled at query time, not re-run on demand
- 22 passing tests; frontend TypeScript build clean

**Design:**
- Single-screen workflow: select → query → evidence → jump → follow-up → report
- Verification badge (model-verified / retrieval-only / mock) prevents false confidence
- Location + camera ID on every live event card — traceability for safety investigations

**Impact — three sponsor tools:**
1. **VAST Data** — semantic search over indexed archive, streaming proxy, segment inventory, explore, metadata
2. **NVIDIA Cosmos** — evidence-grounded reasoning via VSS agent endpoint
3. **YOLO11** — precomputed object detection sidecars per segment

**Honest limitations:**
- W&B is not integrated (env var placeholder exists; no credentials)
- Live Cosmos reasoning depends on VSS agent being active; times out gracefully
- Detection sidecar availability depends on what was indexed at ingest time
