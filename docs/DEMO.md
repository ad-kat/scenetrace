# SceneTrace — 2-Minute Demo Script

**VAST Builders Challenge · Team 34**

---

## Pre-demo checklist

- [ ] `curl -fsS http://localhost:8000/health` returns `"status":"ok"`
- [ ] Frontend open at deployment URL or http://localhost:5173
- [ ] Top badge shows `LIVE · live` (or `DEMO MODE` if in mock fallback — announce it)
- [ ] Have the query "forklift approaching a pedestrian" ready to type

---

## Script (2 minutes)

### 0:00 — Open and orient (10 s)
*"This is SceneTrace — a warehouse safety investigation tool. Safety teams use it to proactively find near-misses in recorded footage, not just review after accidents happen."*

Point to the top badge (LIVE / DEMO MODE).

### 0:10 — Archive-wide search (30 s)
In the **Find Potential Near-Misses** box, type:
> `forklift approaching a pedestrian`

Click **Search Archive**.

*"This sends a semantic search query across the entire indexed video archive — every camera, every location — using VAST's VSS retrieval API."*

**Three result cards appear**, ranked by similarity score. Each shows:
- Timestamp range (e.g. 0:33–0:42)
- Location (Aisle 3) and camera ID (CAM-07)
- A retrieval caption from the indexed metadata
- Match percentage

*"These aren't keyword matches — they're semantically ranked clips from the archive."*

### 0:40 — Load the clip (15 s)
Click the **top result card**.

The video player loads and seeks to 0:33 automatically. The investigation query is pre-filled.

*"Clicking a result loads that exact clip at the relevant timestamp. One click, no scrubbing."*

### 0:55 — Investigate (20 s)
Click **Investigate**.

*"Now SceneTrace runs a deeper analysis: VAST retrieval refines the search to this specific clip, YOLO detections pull precomputed bounding-box data, and Cosmos reasoning answers a structured near-miss question grounded in the indexed evidence."*

**Two evidence cards appear** — each with:
- Exact timestamp
- `[forklift]` and `[person]` labels from YOLO11 detections
- Explanation framed as a potential near-miss, not a confirmed accident
- Verification badge (retrieval-only or model-verified)

### 1:15 — Before/during/after (15 s)
Click **Investigate surrounding footage** on the first event card.

*"This expands a 15-second window — before, during, and after — and runs a fresh retrieval. The investigation timeline shows the chain of turns."*

### 1:30 — Generate safety report (20 s)
Click **Generate Safety Investigation Report**.

The report expands with six structured sections:

*"A — what was observed. B — near-miss assessment. C — possible contributing factors. D — possible consequences. E — preventive recommendations. F — evidence sources and uncertainty."*

Point to section C: *"Notice: 'possible contributing factors' — not 'root cause'. SceneTrace never asserts what it can't see."*

### 1:50 — Tool trace + close (10 s)
Expand the **Tool trace** panel.

*"Every tool call is logged: VAST search, YOLO detection, Cosmos reasoning, with status and latency. Full auditability."*

*"Three sponsor tools. One workflow. Evidence you can stand behind."*

---

## Demo queries (in impact order)

| Query | Expected result |
|---|---|
| `forklift approaching a pedestrian` | 3 results, Aisle 3 / Loading Bay / Junction |
| `worker standing in vehicle path` | pedestrian in vehicle zone |
| `vehicle and pedestrian at intersection` | yard gate incident |
| `person near moving industrial equipment` | default archive hit |

---

## Backup plan — if live VSS is slow or unavailable

The app **automatically falls back to mock mode** if VSS credentials are absent or search times out.

Tell judges: *"We're in demo mode — same workflow, same UI, fixture data instead of live retrieval."*

- All five search queries return deterministic results
- Video player loads the local demo clip
- Investigation, follow-up, and report all work identically
- Mock badge in the header makes this explicit

### If video streaming fails
The investigation flow (search → evidence cards → report) works without video playback. Show the JSON via:
```bash
curl -s -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query":"forklift approaching a pedestrian"}'
```

### Offline fallback (no backend)
Show the pre-run screenshots in `docs/screenshots/` (if prepared) and walk through the JSON structure.
