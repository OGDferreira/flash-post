import React from "react";
import { AbsoluteFill, Sequence, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import timeline from "./timeline.json";
import { C, FONT } from "./theme";
import { clamp } from "./ui";
import type { SceneProps, Word } from "./types";
import { Hook, Pain } from "./scenes/Pain";
import { Reveal, Folders } from "./scenes/Reveal";
import { Loop } from "./scenes/Loop";
import { Schedule } from "./scenes/Schedule";
import { Dashboard } from "./scenes/Dashboard";
import { Team } from "./scenes/Team";
import { Notify, Cta } from "./scenes/Notify";

const SCENES: Record<string, React.FC<SceneProps>> = {
  hook: Hook,
  pain: Pain,
  reveal: Reveal,
  folders: Folders,
  loop: Loop,
  schedule: Schedule,
  dashboard: Dashboard,
  team: Team,
  notify: Notify,
  cta: Cta,
};

const TRANS = 8; // frames of overlap between scenes

/** Ambient background from index.css: drifting brand/violet blobs over #05070f. */
const Background: React.FC = () => {
  const frame = useCurrentFrame();
  const t = frame / 30;
  const drop = interpolate(frame, [timeline.dropSec * 30 - 4, timeline.dropSec * 30 + 10], [0, 1], clamp);
  const blob = (x: number, y: number, r: number, color: string) => (
    <div
      style={{
        position: "absolute",
        left: x - r,
        top: y - r,
        width: r * 2,
        height: r * 2,
        borderRadius: "50%",
        background: `radial-gradient(circle, ${color}, transparent 68%)`,
      }}
    />
  );
  return (
    <AbsoluteFill style={{ background: "#05070f", overflow: "hidden" }}>
      <AbsoluteFill style={{ opacity: 0.35 + drop * 0.65 }}>
        {blob(180 + Math.sin(t / 3) * 120, 300 + Math.cos(t / 4) * 90, 700, "rgba(83,109,254,0.5)")}
        {blob(950 + Math.cos(t / 3.5) * 100, 420 + Math.sin(t / 2.7) * 120, 600, "rgba(0,170,255,0.28)")}
        {blob(900 + Math.sin(t / 4.2) * 110, 1550 + Math.cos(t / 3) * 100, 720, "rgba(150,70,255,0.3)")}
        {blob(150 + Math.cos(t / 3.8) * 90, 1650 + Math.sin(t / 3.3) * 120, 640, "rgba(83,109,254,0.3)")}
      </AbsoluteFill>
      {/* subtle grid */}
      <AbsoluteFill
        style={{
          backgroundImage:
            "linear-gradient(rgba(255,255,255,0.035) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.035) 1px, transparent 1px)",
          backgroundSize: "90px 90px",
          backgroundPosition: `0 ${(frame * 0.6) % 90}px`,
          maskImage: "radial-gradient(circle at 50% 45%, black, transparent 75%)",
        }}
      />
    </AbsoluteFill>
  );
};

/** Wraps a scene with a quick zoom/blur transition in and out. */
const SceneShell: React.FC<{ frames: number; children: React.ReactNode; first?: boolean }> = ({
  frames,
  children,
  first,
}) => {
  const frame = useCurrentFrame();
  const enter = first ? 1 : interpolate(frame, [0, TRANS], [0, 1], clamp);
  const exit = interpolate(frame, [frames, frames + TRANS], [0, 1], clamp);
  return (
    <AbsoluteFill
      style={{
        opacity: enter * (1 - exit),
        transform: `scale(${(1.06 - enter * 0.06) * (1 - exit * 0.05)})`,
        filter: `blur(${(1 - enter) * 12 + exit * 12}px)`,
      }}
    >
      {children}
    </AbsoluteFill>
  );
};

/** TikTok-style captions: 3-word chunks, current word highlighted. */
const Captions: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  for (const s of timeline.scenes) {
    const local = t - s.startSec;
    if (local < 0 || local > s.durSec) continue;
    const words = s.words as Word[];
    const chunks: Word[][] = [];
    let cur: Word[] = [];
    for (const w of words) {
      cur.push(w);
      if (cur.length === 3 || /[.,?!:]$/.test(w.w)) {
        chunks.push(cur);
        cur = [];
      }
    }
    if (cur.length) chunks.push(cur);
    const chunk = chunks.find((c, i) => {
      const next = chunks[i + 1];
      return local >= c[0].s - 0.05 && (next ? local < next[0].s - 0.05 : local <= c[c.length - 1].e + 0.4);
    });
    if (!chunk) return null;
    const long = chunk.reduce((n, w) => n + w.w.length, 0) > 16;
    const pop = interpolate(local, [chunk[0].s - 0.05, chunk[0].s + 0.08], [0.85, 1], clamp);
    // edge-tts word boundaries drop punctuation; restore it from the script text
    return (
      <AbsoluteFill style={{ alignItems: "center", top: 1420, height: 220 }}>
        <div
          style={{
            fontFamily: FONT,
            fontSize: long ? 60 : 72,
            fontWeight: 900,
            letterSpacing: "-0.02em",
            width: 980,
            display: "flex",
            flexWrap: "wrap",
            justifyContent: "center",
            rowGap: 8,
            lineHeight: 1.1,
            transform: `scale(${pop})`,
            textTransform: "uppercase",
          }}
        >
          {chunk.map((w, i) => {
            const active = local >= w.s && local < w.e + 0.12;
            return (
              <span
                key={i}
                style={{
                  color: active ? "#0b1020" : C.fg,
                  background: active ? "linear-gradient(135deg,#7dd8ff,#22c1ee)" : "transparent",
                  borderRadius: 14,
                  padding: "0 12px",
                  margin: "0 2px",
                  WebkitTextStroke: active ? "0" : "2px rgba(0,0,0,0.6)",
                  textShadow: active ? "none" : "0 6px 18px rgba(0,0,0,0.8)",
                  boxDecorationBreak: "clone",
                }}
              >
                {w.w.replace(/,$/, "")}
              </span>
            );
          })}
        </div>
      </AbsoluteFill>
    );
  }
  return null;
};

export const FlashPostVideo: React.FC = () => (
  <AbsoluteFill style={{ background: "#05070f" }}>
    <Background />
    {timeline.scenes.map((s, i) => {
      const Scene = SCENES[s.id];
      return (
        <Sequence key={s.id} from={s.from} durationInFrames={s.frames + TRANS} name={s.id} premountFor={15}>
          <SceneShell frames={s.frames} first={i === 0}>
            <Scene dur={s.frames} words={s.words as Word[]} />
          </SceneShell>
        </Sequence>
      );
    })}
    <Captions />
  </AbsoluteFill>
);
