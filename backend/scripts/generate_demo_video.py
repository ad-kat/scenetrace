"""Generate a deterministic 120-second demo video for mock mode testing.

Usage:
    python backend/scripts/generate_demo_video.py

Requires ffmpeg on PATH. Output: media/demo-01.mp4
The generated video is a solid-color clip with a timecode burn-in — enough for
browser playback and seeking tests. Never commit it to the repo (it is in .gitignore).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


DURATION = 120
OUTPUT = Path(__file__).resolve().parents[2] / "media" / "demo-01.mp4"


def main() -> None:
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found on PATH. Install it with: sudo apt install ffmpeg")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", (
            f"color=c=0x1a1a2e:size=1280x720:duration={DURATION}:rate=15,"
            "drawtext=fontcolor=white:fontsize=48:x=(w-tw)/2:y=(h-th)/2"
            ":text='SceneTrace Demo',"
            "drawtext=fontcolor=yellow:fontsize=32:x=20:y=20"
            ":timecode='00\\:00\\:00\\:00':rate=15:text=''"
        ),
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
        "-an",
        str(OUTPUT),
    ]
    print(f"Generating {OUTPUT} …")
    result = subprocess.run(cmd, shell=False, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr[-800:])
        sys.exit(f"ffmpeg failed (exit {result.returncode})")
    size_mb = OUTPUT.stat().st_size / 1_048_576
    print(f"Done — {OUTPUT} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
