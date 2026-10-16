import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig, Easing } from "remotion";
import { C, FONT, GRAD } from "./theme";

export const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

/** Spring from 0 to 1 starting at `delay` frames. */
export const useIn = (delay = 0, damping = 14, stiffness = 120) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return spring({ frame: frame - delay, fps, config: { damping, stiffness } });
};

export const ramp = (frame: number, a: number, b: number, from = 0, to = 1) =>
  interpolate(frame, [a, b], [from, to], { ...clamp, easing: Easing.bezier(0.22, 1, 0.36, 1) });

export const fmt = (n: number) => Math.round(n).toLocaleString("pt-BR");

export const Glass: React.FC<{
  style?: React.CSSProperties;
  children?: React.ReactNode;
  glow?: string;
}> = ({ style, children, glow }) => (
  <div
    style={{
      background: "rgba(22,28,48,0.78)",
      border: "1.5px solid rgba(255,255,255,0.14)",
      borderRadius: 32,
      boxShadow: `0 18px 50px rgba(0,0,0,0.45), inset 0 1.5px 0 rgba(255,255,255,0.12)${
        glow ? `, 0 0 60px ${glow}` : ""
      }`,
      backdropFilter: "blur(22px)",
      color: C.fg,
      fontFamily: FONT,
      ...style,
    }}
  >
    {children}
  </div>
);

export const Eyebrow: React.FC<{ children: React.ReactNode; color?: string }> = ({ children, color }) => (
  <div
    style={{
      fontSize: 26,
      fontWeight: 700,
      letterSpacing: "0.16em",
      color: color ?? C.neon,
      textTransform: "uppercase",
    }}
  >
    {children}
  </div>
);

export const Title: React.FC<{ children: React.ReactNode; size?: number; style?: React.CSSProperties }> = ({
  children,
  size = 64,
  style,
}) => (
  <div style={{ fontSize: size, fontWeight: 800, letterSpacing: "-0.03em", lineHeight: 1.05, ...style }}>
    {children}
  </div>
);

export const Pill: React.FC<{
  children: React.ReactNode;
  color?: string;
  bg?: string;
  style?: React.CSSProperties;
}> = ({ children, color = C.fg, bg = "rgba(255,255,255,0.08)", style }) => (
  <div
    style={{
      display: "inline-flex",
      alignItems: "center",
      gap: 10,
      padding: "10px 22px",
      borderRadius: 999,
      background: bg,
      color,
      fontSize: 26,
      fontWeight: 650,
      ...style,
    }}
  >
    {children}
  </div>
);

export const PrimaryButton: React.FC<{ children: React.ReactNode; style?: React.CSSProperties }> = ({
  children,
  style,
}) => (
  <div
    style={{
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      gap: 14,
      height: 96,
      borderRadius: 999,
      background: "linear-gradient(145deg,#5169f4,#3b52e0)",
      boxShadow: "0 14px 36px rgba(83,109,254,0.5)",
      color: "#fff",
      fontSize: 36,
      fontWeight: 750,
      ...style,
    }}
  >
    {children}
  </div>
);

export const Bar: React.FC<{ p: number; h?: number; grad?: string; style?: React.CSSProperties }> = ({
  p,
  h = 16,
  grad = `linear-gradient(90deg, ${C.brand}, ${C.neon})`,
  style,
}) => (
  <div style={{ height: h, borderRadius: 999, background: "rgba(255,255,255,0.08)", overflow: "hidden", ...style }}>
    <div style={{ width: `${Math.max(0, Math.min(1, p)) * 100}%`, height: "100%", borderRadius: 999, background: grad }} />
  </div>
);

/** The FlashPost mark, drawn from the same paths as BrandLogo.tsx, with a build-in animation. */
export const Logo: React.FC<{ size?: number; delay?: number; animate?: boolean }> = ({
  size = 200,
  delay = 0,
  animate = true,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = (d: number, damping = 11) =>
    animate ? spring({ frame: frame - delay - d, fps, config: { damping, stiffness: 140 } }) : 1;
  const bg = s(0, 12);
  const f = animate ? ramp(frame, delay + 5, delay + 18) : 1;
  const dot = s(16, 8);
  const tail = s(20, 10);
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" style={{ overflow: "visible" }}>
      <defs>
        <linearGradient id="lg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor={C.gradA} />
          <stop offset="1" stopColor={C.gradB} />
        </linearGradient>
        <clipPath id="fclip">
          <rect x="0" y="0" width={14 + 24 * f} height="64" />
        </clipPath>
      </defs>
      <g transform={`translate(32 32) scale(${bg}) rotate(${(1 - bg) * -30}) translate(-32 -32)`}>
        <rect width="64" height="64" rx="16" fill="url(#lg)" />
      </g>
      <path d="M14 44V20h24v7H22v4h13v7H22v6z" fill="#fff" clipPath="url(#fclip)" />
      <circle cx="46" cy="22" r={5 * dot} fill="#fff" opacity={0.9} />
      <path
        d="M42 44l8-14v10h-5z"
        fill="#fff"
        opacity={0.9 * tail}
        transform={`translate(${(1 - tail) * 8} ${(1 - tail) * -8})`}
      />
    </svg>
  );
};

export const Wordmark: React.FC<{ size?: number }> = ({ size = 96 }) => (
  <div style={{ fontFamily: FONT, fontSize: size, fontWeight: 800, letterSpacing: "-0.04em", color: C.fg }}>
    FlashPost<span style={{ color: "#93a3ff" }}>.</span>
  </div>
);

/** Video thumbnail placeholder: a gradient tile with a play glyph, no real imagery. */
export const Thumb: React.FC<{ i: number; w: number; h: number; style?: React.CSSProperties }> = ({ i, w, h, style }) => {
  const hues = [228, 190, 270, 330, 160, 30, 205, 250];
  const hue = hues[i % hues.length];
  return (
    <div
      style={{
        width: w,
        height: h,
        borderRadius: Math.min(w, h) * 0.14,
        background: `linear-gradient(160deg, hsl(${hue} 80% 62%), hsl(${(hue + 40) % 360} 70% 32%))`,
        position: "relative",
        overflow: "hidden",
        flexShrink: 0,
        ...style,
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: "radial-gradient(circle at 30% 25%, rgba(255,255,255,0.35), transparent 55%)",
        }}
      />
      <svg
        viewBox="0 0 24 24"
        width={Math.min(w, h) * 0.32}
        style={{ position: "absolute", left: "50%", top: "50%", transform: "translate(-50%,-50%)" }}
      >
        <circle cx="12" cy="12" r="11" fill="rgba(0,0,0,0.3)" />
        <path d="M10 8l6 4-6 4z" fill="#fff" />
      </svg>
    </div>
  );
};

export const Avatar: React.FC<{ name: string; size?: number; hue?: number }> = ({ name, size = 72, hue = 228 }) => (
  <div
    style={{
      width: size,
      height: size,
      borderRadius: "50%",
      background: `linear-gradient(140deg, hsl(${hue} 75% 62%), hsl(${(hue + 50) % 360} 70% 42%))`,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      color: "#fff",
      fontWeight: 800,
      fontSize: size * 0.42,
      flexShrink: 0,
      border: "3px solid rgba(255,255,255,0.18)",
    }}
  >
    {name[0]}
  </div>
);

/** iOS-style notification banner (app name only, no "from" line). */
export const Notification: React.FC<{
  title: string;
  body: string;
  time?: string;
  style?: React.CSSProperties;
}> = ({ title, body, time = "agora", style }) => (
  <div
    style={{
      display: "flex",
      gap: 26,
      padding: "28px 30px",
      borderRadius: 44,
      background: "rgba(38,40,52,0.86)",
      border: "1px solid rgba(255,255,255,0.1)",
      boxShadow: "0 20px 50px rgba(0,0,0,0.5)",
      backdropFilter: "blur(30px)",
      fontFamily: FONT,
      color: C.fg,
      ...style,
    }}
  >
    <div style={{ flexShrink: 0, marginTop: 4 }}>
      <Logo size={88} animate={false} />
    </div>
    <div style={{ flex: 1, minWidth: 0 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <div style={{ fontSize: 33, fontWeight: 700 }}>{title}</div>
        <div style={{ fontSize: 26, color: "rgba(255,255,255,0.5)", flexShrink: 0, marginLeft: 16 }}>{time}</div>
      </div>
      <div style={{ fontSize: 31, lineHeight: 1.3, color: "rgba(255,255,255,0.92)", marginTop: 4 }}>{body}</div>
    </div>
  </div>
);

/** A tap indicator: ripple at (x, y) peaking at frame `at`. */
export const Tap: React.FC<{ x: number; y: number; at: number }> = ({ x, y, at }) => {
  const frame = useCurrentFrame();
  const t = frame - at;
  if (t < -14 || t > 16) return null;
  const approach = interpolate(t, [-14, 0], [0, 1], clamp);
  const ring = interpolate(t, [0, 16], [0, 1], clamp);
  return (
    <div style={{ position: "absolute", left: x, top: y, pointerEvents: "none" }}>
      <div
        style={{
          position: "absolute",
          width: 70,
          height: 70,
          left: -35,
          top: -35,
          borderRadius: "50%",
          background: "rgba(255,255,255,0.85)",
          opacity: approach * (1 - ring),
          transform: `scale(${t < 0 ? 1.3 - approach * 0.3 : 1 - ring * 0.2})`,
          boxShadow: "0 0 30px rgba(255,255,255,0.6)",
        }}
      />
      <div
        style={{
          position: "absolute",
          width: 70,
          height: 70,
          left: -35,
          top: -35,
          borderRadius: "50%",
          border: "4px solid #fff",
          opacity: t >= 0 ? 1 - ring : 0,
          transform: `scale(${1 + ring * 1.6})`,
        }}
      />
    </div>
  );
};

export { GRAD };
