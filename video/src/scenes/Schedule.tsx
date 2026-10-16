import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { CalendarClock, CheckCircle2 } from "lucide-react";
import { C, FONT } from "../theme";
import { Eyebrow, Glass, PrimaryButton, Tap, Thumb, Title, useIn } from "../ui";
import type { SceneProps } from "../types";
import { wordAt } from "../types";

const TIMES = ["12:00", "18:00", "19:00", "21:00"];
const CELL = 112;

/** Schedule: pick a day and time for a single post of your own. */
export const Schedule: React.FC<SceneProps> = ({ words }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const agende = wordAt(words, "Agende", fps);
  const day = wordAt(words, "dia", fps);
  const hour = wordAt(words, "hora", fps);
  const done = wordAt(words, "exatos", fps) + 12;
  const head = useIn(0, 15);
  const card = useIn(6, 15);
  const ok = useIn(done, 12, 170);
  // October 2026 starts on a Thursday (index 4, Sunday-first grid)
  const cells = [...Array(4).fill(null), ...Array.from({ length: 31 }, (_, i) => i + 1)];
  return (
    <AbsoluteFill style={{ fontFamily: FONT, color: C.fg, padding: "170px 70px 0" }}>
      <div style={{ opacity: head }}>
        <Eyebrow>Publicação própria</Eyebrow>
        <Title style={{ marginTop: 10, display: "flex", alignItems: "center", gap: 18 }}>
          <CalendarClock size={64} color={C.neon} /> Agendar publicação
        </Title>
      </div>
      <Glass style={{ marginTop: 36, padding: 32, opacity: card, transform: `translateY(${(1 - card) * 80}px)` }}>
        <div style={{ display: "flex", gap: 24, alignItems: "center" }}>
          <Thumb i={5} w={130} h={180} />
          <div>
            <div style={{ fontSize: 26, color: C.muted }}>@cortes.humor · Reels</div>
            <div style={{ fontSize: 32, fontWeight: 650, marginTop: 8 }}>“Episódio novo hoje 🔥 comenta EU”</div>
          </div>
        </div>
        <div style={{ marginTop: 28, fontSize: 32, fontWeight: 750 }}>Outubro 2026</div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: `repeat(7, ${CELL}px)`,
            gap: 6,
            marginTop: 14,
            fontSize: 28,
            textAlign: "center",
          }}
        >
          {["D", "S", "T", "Q", "Q", "S", "S"].map((d, i) => (
            <div key={i} style={{ color: C.muted, fontSize: 24, fontWeight: 700 }}>
              {d}
            </div>
          ))}
          {cells.map((d, i) => {
            const picked = d === 17 && frame >= day;
            const today = d === 16;
            return (
              <div
                key={i}
                style={{
                  height: 66,
                  lineHeight: "66px",
                  borderRadius: 18,
                  fontWeight: picked || today ? 800 : 500,
                  color: d && d < 16 ? "rgba(255,255,255,0.3)" : C.fg,
                  background: picked ? "linear-gradient(145deg,#5169f4,#3b52e0)" : "transparent",
                  border: today ? `2px solid ${C.neon}` : "2px solid transparent",
                  transform: picked && frame < day + 6 ? "scale(1.15)" : "none",
                }}
              >
                {d ?? ""}
              </div>
            );
          })}
        </div>
        <div style={{ display: "flex", gap: 14, marginTop: 24 }}>
          {TIMES.map((t) => {
            const picked = t === "19:00" && frame >= hour;
            return (
              <div
                key={t}
                style={{
                  flex: 1,
                  textAlign: "center",
                  padding: "18px 0",
                  borderRadius: 999,
                  fontSize: 30,
                  fontWeight: 700,
                  background: picked ? "linear-gradient(145deg,#5169f4,#3b52e0)" : "rgba(255,255,255,0.07)",
                  boxShadow: picked ? "0 8px 22px rgba(83,109,254,0.45)" : "none",
                }}
              >
                {t}
              </div>
            );
          })}
        </div>
        <PrimaryButton style={{ marginTop: 26, opacity: frame >= agende ? 1 : 0.5 }}>Agendar publicação</PrimaryButton>
      </Glass>
      {/* tap targets (absolute, page coordinates) */}
      <Tap x={70 + 32 + 6 * (CELL + 6) + CELL / 2} y={day ? 742 + 3 * 72 + 33 : 0} at={day} />
      <Tap x={70 + 32 + 2 * 223 + 100} y={1100} at={hour} />
      <Tap x={540} y={1230} at={done - 6} />
      <div
        style={{
          position: "absolute",
          left: 90,
          right: 90,
          top: 1110,
          padding: "30px 34px",
          borderRadius: 28,
          background: "rgba(20,60,48,0.95)",
          border: "2px solid #7ee2bd",
          display: "flex",
          alignItems: "center",
          gap: 20,
          fontSize: 34,
          fontWeight: 750,
          opacity: ok,
          transform: `scale(${0.7 + ok * 0.3})`,
          boxShadow: "0 20px 50px rgba(0,0,0,0.5)",
        }}
      >
        <CheckCircle2 size={52} color="#7ee2bd" />
        Agendado para sáb., 17/10 às 19:00
      </div>
    </AbsoluteFill>
  );
};
