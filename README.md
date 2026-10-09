# SceneTrace

Evidence-grounded agent for investigating recorded video. Built for the VAST Builders Challenge (Real-Time Video Agents Hack).

## Quick start

### Prerequisites
- Python 3.12, Node 20, ffmpeg

### Backend (WSL2 / macOS)

```bash
cd ~/scenetrace/backend
python3 -m venv tracenv           # first time only
source tracenv/bin/activate       # Windows: tracenv\Scripts\activate
pip install -r requirements.txt
pip install pydantic-settings     # if not already present

# Generate demo video (first time)
ffmpeg -y -f lavfi \
  -i "color=c=0x1a2a4a:size=640x360:rate=25,drawtext=fontcolor=white:fontsize=28:x=20:y=20:text='SceneTrace Demo'" \
  -f lavfi -i "sine=frequency=440:sample_rate=44100" \
  -map 0:v -map 1:a -c:v libx264 -preset ultrafast -crf 28 \
  -c:a aac -b:a 64k -t 120 ../media/demo-01.mp4

# Start server
SCENETRACE_MEDIA_DIR=../media uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd ~/scenetrace/frontend
npm install
npm run dev      # dev server at http://localhost:5173
```

### Run tests

```bash
cd ~/scenetrace/backend
source tracenv/bin/activate
SCENETRACE_MEDIA_DIR=../media pytest -q
```

### Verify

```bash
curl -fsS http://localhost:8000/health
curl -fsS -X POST http://localhost:8000/api/investigate \
  -H "Content-Type: application/json" \
  -d '{"video_id":"demo-01","query":"Find when someone sets down a box"}'
```

## Configuration

Copy `.env.example` to `.env` and set values as needed.

| Variable | Default | Description |
|---|---|---|
| `SCENETRACE_MODE` | `mock` | `mock` \| `live` \| `hybrid` |
| `SCENETRACE_MEDIA_DIR` | `./media` | Path to demo video directory |
| `SCENETRACE_CORS_ORIGINS` | `http://localhost:5173` | Allowed origins |
| `VAST_API_URL` | _(empty)_ | Fill after event onboarding |
| `VAST_API_KEY` | _(empty)_ | Fill after event onboarding |
| `NVIDIA_API_KEY` | _(empty)_ | Fill after event onboarding |

## What works (MVP)

- `GET /health` → provider mode
- `GET /api/videos` → demo video registry with probed duration
- `GET /api/videos/{id}/file` → byte-range serving for browser seek
- `POST /api/investigate` → deterministic mock search, evidence cards, tool trace
- Session-scoped follow-up via `selected_event_id`
- React single-page app: video selector, player, timeline, evidence cards, inspect/follow-up
- MOCK mode badge — all fixture output clearly labeled

## Integrations

All sponsor APIs (VAST, Cosmos, YOLO, W&B) are stubbed pending event onboarding.
See `docs/INTEGRATION_NOTES.md`.
