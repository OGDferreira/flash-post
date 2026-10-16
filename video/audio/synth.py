"""Procedural music + sound effects for the FlashPost promo.

Everything is synthesized from scratch with numpy, so the soundtrack carries no
third-party rights. Usage: python3 synth.py <timeline.json> <out_dir>
"""

import json
import sys
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt

SR = 48000
rng = np.random.default_rng(7)


def t_axis(sec):
    return np.arange(int(sec * SR)) / SR


def lowpass(x, hz, order=4):
    return sosfilt(butter(order, hz, "low", fs=SR, output="sos"), x)


def highpass(x, hz, order=4):
    return sosfilt(butter(order, hz, "high", fs=SR, output="sos"), x)


def bandpass(x, lo, hi, order=2):
    return sosfilt(butter(order, [lo, hi], "band", fs=SR, output="sos"), x)


def env(n, a=0.005, d=0.2, s=0.0, r=0.05, sus_len=None):
    a_n, d_n, r_n = int(a * SR), int(d * SR), int(r * SR)
    sus_n = max(0, n - a_n - d_n - r_n) if sus_len is None else int(sus_len * SR)
    e = np.concatenate([
        np.linspace(0, 1, max(a_n, 1)),
        np.linspace(1, s, max(d_n, 1)),
        np.full(sus_n, s),
        np.linspace(s, 0, max(r_n, 1)),
    ])
    if len(e) < n:
        e = np.pad(e, (0, n - len(e)))
    return e[:n]


def saw(freq, t):
    return 2 * ((freq * t) % 1.0) - 1


def note_hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def add(buf, sig, at):
    i = int(at * SR)
    if i >= len(buf):
        return
    end = min(len(buf), i + len(sig))
    buf[i:end] += sig[: end - i]


# ---------------- instruments ----------------

def kick():
    t = t_axis(0.45)
    f = 50 + 110 * np.exp(-t * 28)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * np.exp(-t * 7) * 1.0 + np.sin(ph * 2) * np.exp(-t * 40) * 0.15


def clap():
    t = t_axis(0.25)
    n = rng.standard_normal(len(t))
    bursts = sum(np.exp(-np.clip(t - k * 0.011, 0, None) * 60) * (t >= k * 0.011) for k in range(3))
    return bandpass(n, 900, 3500) * bursts * np.exp(-t * 14) * 0.9


def hat(open_=False):
    t = t_axis(0.25 if open_ else 0.06)
    n = highpass(rng.standard_normal(len(t)), 7000)
    return n * np.exp(-t * (14 if open_ else 70)) * 0.35


def bass_note(midi, dur):
    t = t_axis(dur)
    f = note_hz(midi)
    x = saw(f, t) * 0.6 + np.sin(2 * np.pi * f * t) * 0.6
    return lowpass(x, 420) * env(len(t), 0.004, dur * 0.6, 0.5, 0.03) * 0.55


def pad_chord(midis, dur, cutoff=1800):
    t = t_axis(dur)
    x = np.zeros_like(t)
    for m in midis:
        for det in (-0.12, 0.0, 0.12):
            x += saw(note_hz(m + det), t + rng.random() * 0.01)
    x /= len(midis) * 3
    return lowpass(x, cutoff, 2) * env(len(t), 0.35, 0.3, 0.8, 0.5) * 0.4


def pluck(midi, dur=0.28):
    t = t_axis(dur)
    f = note_hz(midi)
    x = saw(f, t) * 0.5 + np.sign(np.sin(2 * np.pi * f * t)) * 0.2
    x = lowpass(x, 3200, 2)
    return x * np.exp(-t * 11) * 0.28


# Am - F - C - G (one bar each)
PROG = [
    (45, [57, 60, 64]),
    (41, [57, 60, 65]),
    (48, [55, 60, 64]),
    (43, [55, 59, 62]),
]


def music(total, drop_at, bpm=122):
    beat = 60 / bpm
    bar = beat * 4
    buf = np.zeros(int((total + 2) * SR))
    n_bars = int(np.ceil(total / bar)) + 1
    # snap the drop to the bar grid so the beat lands on the "FlashPost" reveal
    drop_bar = int(round(drop_at / bar))
    offset = drop_at - drop_bar * bar  # shift the whole grid so a bar starts at drop_at
    for b in range(n_bars + 1):
        t0 = offset + b * bar
        if t0 < -bar:
            continue
        root, chord = PROG[b % 4]
        intro = b < drop_bar
        if t0 >= 0 or t0 + bar > 0:
            pc = pad_chord(chord, bar + 0.4, 900 if intro else 2200)
            if t0 < 0:
                pc = pc[int(-t0 * SR):]
                add(buf, pc, 0)
            else:
                add(buf, pc * (0.9 if intro else 0.7), t0)
        for k in range(4):
            tb = t0 + k * beat
            if tb < 0:
                continue
            if intro:
                # tense heartbeat pulse during the "pain" section
                if k in (0, 2):
                    add(buf, kick() * 0.45, tb)
                add(buf, bass_note(root, beat * 0.9) * 0.55, tb)
            else:
                add(buf, kick(), tb)
                if k in (1, 3):
                    add(buf, clap(), tb)
                add(buf, hat(), tb + beat / 2)
                add(buf, hat() * 0.5, tb + beat / 4 * 3)
                add(buf, bass_note(root, beat * 0.45), tb + beat / 2)
                add(buf, bass_note(root + 12 if k == 3 else root, beat * 0.3), tb + beat * 0.75)
                arp = [chord[0] + 12, chord[1] + 12, chord[2] + 12, chord[1] + 12]
                add(buf, pluck(arp[k]), tb)
                add(buf, pluck(arp[(k + 2) % 4]) * 0.7, tb + beat / 2)
    buf = buf[: int(total * SR)]
    # fade in/out
    fi, fo = int(0.8 * SR), int(2.0 * SR)
    buf[:fi] *= np.linspace(0, 1, fi)
    buf[-fo:] *= np.linspace(1, 0, fo)
    return buf


# ---------------- sound effects ----------------

def sfx_whoosh(dur=0.55):
    t = t_axis(dur)
    n = rng.standard_normal(len(t))
    sweep = np.linspace(300, 6000, len(t)) ** 1.0
    out = np.zeros_like(n)
    # crude time-varying bandpass: process in chunks
    step = 1024
    for i in range(0, len(n), step):
        c = sweep[min(i, len(sweep) - 1)]
        out[i:i + step] = bandpass(n[max(0, i - 2048):i + step], c * 0.6, min(c * 1.6, SR / 2 - 100))[-len(n[i:i + step]):]
    shape = np.sin(np.pi * np.linspace(0, 1, len(t))) ** 2
    return out * shape * 0.5


def sfx_pop():
    t = t_axis(0.12)
    f = 900 * np.exp(-t * 18) + 300
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 35) * 0.5


def sfx_click():
    t = t_axis(0.03)
    return highpass(rng.standard_normal(len(t)), 2000) * np.exp(-t * 250) * 0.4


def sfx_ding():
    """iOS-ish notification chime (two bell tones)."""
    out = np.zeros(int(0.9 * SR))
    for at, m in ((0.0, 88), (0.11, 93)):
        t = t_axis(0.8)
        f = note_hz(m)
        bell = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * f * 2.76 * t) * np.exp(-t * 6)
        add(out, bell * np.exp(-t * 5) * 0.32, at)
    return out


def sfx_cash():
    """Cha-ching: metallic hit + bright bell."""
    t = t_axis(0.9)
    hit = highpass(rng.standard_normal(len(t)), 3000) * np.exp(-t * 40) * 0.35
    out = hit.copy()
    for at, m in ((0.06, 96), (0.06, 100), (0.16, 103)):
        tt = t_axis(0.7)
        f = note_hz(m)
        b = np.sin(2 * np.pi * f * tt) + 0.4 * np.sin(2 * np.pi * f * 3.01 * tt)
        add(out, b * np.exp(-tt * 6) * 0.22, at)
    return out


def sfx_riser(dur=1.6):
    t = t_axis(dur)
    n = rng.standard_normal(len(t))
    noise = highpass(n, 1500) * np.linspace(0, 1, len(t)) ** 2 * 0.35
    f = 200 * 2 ** (np.linspace(0, 3, len(t)))
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.linspace(0, 1, len(t)) ** 2 * 0.15
    return noise + tone


def sfx_impact():
    t = t_axis(1.6)
    f = 38 + 60 * np.exp(-t * 9)
    boom = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 2.5)
    crack = lowpass(rng.standard_normal(len(t)), 2500) * np.exp(-t * 18) * 0.6
    return (boom + crack) * 0.8


def sfx_error():
    t = t_axis(0.35)
    x = np.sign(np.sin(2 * np.pi * 180 * t)) * 0.2 + np.sin(2 * np.pi * 170 * t) * 0.2
    return lowpass(x, 1500) * env(len(t), 0.005, 0.1, 0.7, 0.08)


SFX = {
    "whoosh": sfx_whoosh,
    "pop": sfx_pop,
    "click": sfx_click,
    "ding": sfx_ding,
    "cash": sfx_cash,
    "riser": sfx_riser,
    "impact": sfx_impact,
    "error": sfx_error,
}


def main():
    timeline = json.loads(Path(sys.argv[1]).read_text())
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    total = timeline["durationSec"]

    m = music(total, timeline["dropSec"])
    fx = np.zeros(int(total * SR) + SR * 2)
    for ev in timeline["sfx"]:
        add(fx, SFX[ev["type"]]() * ev.get("gain", 1.0), ev["at"])
    fx = fx[: int(total * SR)]

    def save(name, x, peak=0.9):
        x = x / (np.max(np.abs(x)) + 1e-9) * peak
        wavfile.write(out_dir / name, SR, (x * 32767).astype(np.int16))

    save("music.wav", m)
    save("sfx.wav", fx, 0.95)


if __name__ == "__main__":
    main()
