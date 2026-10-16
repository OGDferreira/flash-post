"""Mix narration, music (ducked under the voice) and SFX, then mux with the video.

Usage: python3 mix.py <silent.mp4> <out.mp4>
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
tl = json.loads((ROOT / "src" / "timeline.json").read_text())
video, out = sys.argv[1], sys.argv[2]
audio_dir = ROOT / "out" / "audio"

inputs = ["-i", video, "-i", str(audio_dir / "music.wav"), "-i", str(audio_dir / "sfx.wav")]
voice_labels, filters = [], []
for i, s in enumerate(tl["scenes"]):
    inputs += ["-i", str(ROOT / "public" / s["voice"])]
    ms = int(s["startSec"] * 1000)
    filters.append(f"[{i + 3}:a]aresample=48000,adelay={ms}|{ms},apad[v{i}]")
    voice_labels.append(f"[v{i}]")

total = tl["durationSec"]
filters += [
    f"{''.join(voice_labels)}amix=inputs={len(voice_labels)}:normalize=0,atrim=0:{total},"
    "highpass=f=80,acompressor=threshold=-18dB:ratio=3:attack=5:release=120,volume=1.6,asplit=2[voice][key]",
    "[1:a]volume=0.55[music]",
    "[music][key]sidechaincompress=threshold=0.04:ratio=6:attack=20:release=350[ducked]",
    "[2:a]volume=0.55[fx]",
    f"[voice][ducked][fx]amix=inputs=3:normalize=0,atrim=0:{total},"
    "loudnorm=I=-14:TP=-1.0:LRA=11[aout]",
]

cmd = [
    "ffmpeg", "-y", *inputs,
    "-filter_complex", ";".join(filters),
    "-map", "0:v", "-map", "[aout]",
    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
    "-movflags", "+faststart", "-shortest", out,
]
subprocess.run(cmd, check=True)
print("wrote", out)
