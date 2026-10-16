"""Generate the PT-BR narration per scene and build timeline.json.

Each scene's length follows its narration, so the visuals always stay in sync
with the voice. Usage: python3 narrate.py
"""

import asyncio
import json
import ssl
import subprocess
from pathlib import Path

import certifi

CA = "/root/.ccr/ca-bundle.crt"
certifi.where = lambda: CA  # the session proxy re-terminates TLS
import edge_tts  # noqa: E402
import edge_tts.communicate as _c  # noqa: E402

_c._SSL_CTX = ssl.create_default_context(cafile=CA)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "public" / "voice"
VOICE = "pt-BR-AntonioNeural"
RATE = "+22%"
FPS = 30
PAD_AFTER = 0.3  # breathing room after each line

SCRIPT = json.loads((ROOT / "audio" / "script.json").read_text())


def duration(path):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", str(path),
    ])
    return float(out)


async def synth(text, path):
    """Save the mp3 and return word timings (seconds) for the captions."""
    words = []
    comm = edge_tts.Communicate(text, VOICE, rate=RATE, boundary="WordBoundary")
    with open(path, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                words.append({
                    "w": chunk["text"],
                    "s": round(chunk["offset"] / 1e7, 3),
                    "e": round((chunk["offset"] + chunk["duration"]) / 1e7, 3),
                })
    return words


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    t = 0.4
    scenes, sfx = [], []
    for i, scene in enumerate(SCRIPT["scenes"]):
        path = OUT / f"{i:02d}-{scene['id']}.mp3"
        words_path = path.with_suffix(".json")
        if not path.exists() or not words_path.exists():
            words_path.write_text(json.dumps(await synth(scene["text"], path), ensure_ascii=False))
        words = json.loads(words_path.read_text())
        tokens = scene["text"].split()
        if len(tokens) == len(words):  # restore punctuation for caption line breaks
            for w, tok in zip(words, tokens):
                w["w"] = tok
        d = duration(path) + PAD_AFTER + scene.get("extra", 0)
        scenes.append({
            "id": scene["id"],
            "text": scene["text"],
            "voice": f"voice/{path.name}",
            "startSec": round(t, 3),
            "durSec": round(d, 3),
            "from": round(t * FPS),
            "frames": round(d * FPS),
            "words": words,
        })
        for ev in scene.get("sfx", []):
            at = ev.get("at", 0)
            if "word" in ev:  # anchor the effect to a spoken word
                norm = lambda x: "".join(ch for ch in x.lower() if ch.isalnum())
                at += next(w["s"] for w in words if norm(w["w"]) == norm(ev["word"]))
            sfx.append({"type": ev["type"], "gain": ev.get("gain", 1.0), "at": round(t + at, 3)})
        t += d
    total = t + 1.2
    drop = next(s["startSec"] for s in scenes if s["id"] == SCRIPT["dropScene"])
    timeline = {
        "fps": FPS,
        "durationSec": round(total, 3),
        "durationFrames": round(total * FPS),
        "dropSec": drop,
        "scenes": scenes,
        "sfx": sfx,
    }
    (ROOT / "src" / "timeline.json").write_text(json.dumps(timeline, ensure_ascii=False, indent=2))
    print(f"total {total:.1f}s, drop at {drop:.2f}s")
    for s in scenes:
        print(f"{s['startSec']:6.2f} {s['durSec']:5.2f}  {s['id']}")


asyncio.run(main())
