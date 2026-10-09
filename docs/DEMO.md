# SceneTrace — 90-Second Demo Script

## Setup (before demo)
Backend running at localhost:8000, frontend at localhost:5173.

## Script

**0:00 — Open app**
"This is SceneTrace — you give it a natural-language question about a video and it returns timestamped evidence, not just a summary."

**0:10 — Show video selector**
Select "SceneTrace Demo Footage." Video plays.

**0:20 — Run first query**
Type: `Find when someone sets down a box`
Click Investigate. Point to the loading indicator.

**0:30 — Evidence cards appear**
"Each result has a precise start–end time, a retrieval evidence entry, and a verification badge. In mock mode you see ⚙ MOCK — when a real provider is wired in, the badge changes."

**0:40 — Jump to moment**
Click the timestamp on event #1. Video seeks to exactly 0:12.
"The timeline marker shows where this event lives in the full footage."

**0:55 — Follow up**
Click "Follow up" on event #1.
"It expands a 15-second window around that moment and runs a fresh search — same session, same video, no hallucinated cross-session memory."

**1:10 — Show tool trace**
Expand "Tool trace" panel.
"Every tool call is logged with its status and latency. When Cosmos or VAST are wired in, their entries appear here."

**1:20 — Close**
"Zero fabricated timestamps. All fixture output is clearly labeled. Real provider adapters are ready to plug in once we get credentials."

## Demo queries

| Query | Expected events |
|---|---|
| Find when someone sets down a box | 12 s, 47 s |
| person walking | 5 s, 65 s |
| door opening | 30 s |
| vehicle passing | 88 s |
| any activity | 20 s |
