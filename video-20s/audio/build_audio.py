"""Music bed + SFX for the 20 s film, anchored to the same word frames as index.html (film/beats.json).

Writes film/audio/{music.wav, sfx/*.wav, events.json}; mix with motionmaxxing's mix.py (see README).
"""
import json, sys
from pathlib import Path
import numpy as np
from scipy.io import wavfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "video" / "audio"))
import synth  # noqa: E402  (procedural instruments + SFX from the 66 s VSL)

ROOT = Path(__file__).resolve().parents[1]
FILM = ROOT / "film"
OUT = FILM / "audio"
(OUT / "sfx").mkdir(parents=True, exist_ok=True)
W = json.loads((FILM / "beats.json").read_text())["words"]
FPS, DUR = 30, 630 / 30
on = lambda i: W[i]["onsetFrame"]
B2, B3, B4, B5, B6, B7 = on(10) - 4, on(20) - 6, on(30) - 6, on(37) - 8, on(42) - 6, on(52) - 6

def save(name, x, peak=0.9):
    x = x / (np.max(np.abs(x)) + 1e-9) * peak
    wavfile.write(OUT / name, synth.SR, (x * 32767).astype(np.int16))

for k, fn in synth.SFX.items():
    save(f"sfx/{k}.wav", fn())
save("music.wav", synth.music(DUR + 1, B2 / FPS, bpm=124))

ev = []
add = lambda frame, kind, gain: ev.append({"t": round(frame / FPS, 3), "sfx": f"sfx/{kind}.wav", "gain": gain})
add(0, "whoosh", -16)
for i in (3, 4, 5, 6, 7, 9):                       # each "Conectar conta" sheet lands
    add(on(i), "pop", -17)
add(B2 - 6, "whoosh", -10); add(B2, "impact", -9)
for k in (0, 6, 12):                                # accounts pour in
    add(on(14) + k, "pop", -18)
add(on(17) + 4, "whoosh", -13)                      # accounts fly into the folders
add(B3 - 4, "whoosh", -11); add(on(22), "pop", -16)
for i in (25, 26, 28, 29):                          # each profile publishes
    add(on(i), "click", -14)
add(on(26), "ding", -15)
add(B4 - 4, "whoosh", -11); add(on(35), "ding", -14)   # Ana overtakes
add(B5 - 4, "whoosh", -11); add(B5 + 10, "cash", -10); add(on(41) + 6, "ding", -12)
add(B6 - 4, "whoosh", -12)
add(on(44), "click", -9); add(on(46) + 1, "click", -9)       # taps on Rosa, Verde
add(on(49) - 32, "riser", -12); add(on(48) + 12, "click", -9); add(on(49), "impact", -11)
add(B7 - 4, "whoosh", -12); add(on(57) - 2, "impact", -8); add(on(58) + 26, "click", -9)
(OUT / "events.json").write_text(json.dumps(ev, indent=1))
print(len(ev), "events; drop at", round(B2 / FPS, 2), "s")
