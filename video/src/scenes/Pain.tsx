import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { AlertTriangle, Clock3, HelpCircle, XCircle } from "lucide-react";
import { C, FONT } from "../theme";
import { clamp, Glass, ramp, Tap, Thumb, useIn } from "../ui";
import type { SceneProps } from "../types";
import { wordAt } from "../types";

/** Hook: the manual grind, video by video, account by account. */
export const Hook: React.FC<SceneProps> = ({ words }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const phoneIn = useIn(2, 16);
  const second = wordAt(words, "conta", fps);
  const video = Math.min(40, 1 + Math.floor(Math.max(0, frame - 30) / 6));
  const account = Math.min(15, 1 + Math.floor(Math.max(0, frame - 30) / 14));
  const shake = frame > 30 ? Math.sin(frame * 1.7) * 2 : 0;
  const t1 = useIn(0, 12);
  const t2 = useIn(second, 12);
  return (
    <AbsoluteFill style={{ fontFamily: FONT, color: C.fg, alignItems: "center" }}>
      <div style={{ position: "absolute", top: 170, textAlign: "center", width: "100%" }}>
        <div
          style={{
            fontSize: 92,
            fontWeight: 900,
            letterSpacing: "-0.04em",
            transform: `scale(${t1})`,
            opacity: frame >= second ? 0.35 : 1,
          }}
        >
          VÍDEO POR VÍDEO
        </div>
        <div
          style={{
            fontSize: 92,
            fontWeight: 900,
            letterSpacing: "-0.04em",
            color: C.danger,
            transform: `scale(${t2})`,
            marginTop: 6,
          }}
        >
          CONTA POR CONTA
        </div>
      </div>

      {/* pile of pending uploads behind the phone */}
      {Array.from({ length: 7 }).map((_, i) => {
        const p = ramp(frame, 20 + i * 12, 34 + i * 12);
        const side = i % 2 ? 1 : -1;
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              top: 640 + (i % 3) * 120,
              left: 540 + side * (330 + (i % 3) * 30) - 90,
              opacity: p,
              transform: `translateY(${(1 - p) * -500}px) rotate(${side * (8 + i * 3)}deg)`,
            }}
          >
            <Thumb i={i} w={180} h={300} />
          </div>
        );
      })}

      <div
        style={{
          position: "absolute",
          top: 470,
          width: 520,
          height: 900,
          borderRadius: 70,
          background: "#05070f",
          border: "10px solid #23293b",
          boxShadow: "0 40px 90px rgba(0,0,0,0.6)",
          transform: `translateY(${(1 - phoneIn) * 900}px) rotate(${shake * 0.4}deg)`,
          overflow: "hidden",
          padding: 30,
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 26, fontWeight: 700 }}>
          <span>Nova publicação</span>
          <span style={{ color: "#4c9dff" }}>Compartilhar</span>
        </div>
        <Thumb i={video} w={440} h={560} style={{ marginTop: 26 }} />
        <div style={{ marginTop: 26, display: "flex", flexDirection: "column", gap: 14 }}>
          <Glass style={{ padding: "16px 22px", borderRadius: 20, fontSize: 26 }}>
            Vídeo <b>{video}</b> de 40
          </Glass>
          <Glass style={{ padding: "16px 22px", borderRadius: 20, fontSize: 26 }}>
            Conta <b>{account}</b> de 15
          </Glass>
        </div>
      </div>
      {[36, 48, 60, 72, 84, 96, 108].map((at) => (
        <Tap key={at} x={720} y={505} at={at} />
      ))}
    </AbsoluteFill>
  );
};

const PROBLEMS = [
  { icon: XCircle, title: "Publicação falhou", sub: "Reels · @cortes.humor", color: C.danger },
  { icon: Clock3, title: "Postado às 03:14", sub: "Fora do horário de pico", color: C.amber },
  { icon: AlertTriangle, title: "@noticias.dia esquecida", sub: "Sem posts há 4 dias", color: C.amber },
  { icon: HelpCircle, title: "Vendas de hoje: ???", sub: "Nenhum dado", color: C.danger },
];

/** Pain: everything that goes wrong when you do it by hand. */
export const Pain: React.FC<SceneProps> = ({ words }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const end = wordAt(words, "Isso", fps);
  const hours = interpolate(frame, [0, end], [0, 192], clamp);
  const slam = useIn(end, 9, 200);
  const collapse = ramp(frame, end - 4, end + 8);
  const shake = frame >= end && frame < end + 12 ? Math.sin(frame * 3) * 14 * (1 - (frame - end) / 12) : 0;
  return (
    <AbsoluteFill style={{ fontFamily: FONT, color: C.fg, transform: `translateX(${shake}px)` }}>
      <AbsoluteFill
        style={{
          background: "radial-gradient(circle at 50% 40%, rgba(255,60,90,0.22), transparent 65%)",
          opacity: 1 - collapse,
        }}
      />
      <div style={{ position: "absolute", top: 200, width: "100%", textAlign: "center", opacity: 1 - collapse }}>
        <div style={{ fontSize: 30, color: C.muted, fontWeight: 650, letterSpacing: "0.12em" }}>
          TEMPO NO CELULAR HOJE
        </div>
        <div
          style={{
            fontSize: 170,
            fontWeight: 900,
            letterSpacing: "-0.05em",
            color: C.danger,
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {Math.floor(hours / 60)}h{String(Math.floor(hours % 60)).padStart(2, "0")}
        </div>
      </div>
      <div style={{ position: "absolute", top: 520, left: 80, right: 80, display: "flex", flexDirection: "column", gap: 26 }}>
        {PROBLEMS.map((p, i) => {
          const at = wordAt(words, ["horas", "post", "esquecida", "sabe"][i], fps) - (i === 2 ? 8 : 0);
          const s = useIn(at, 12, 170);
          const Icon = p.icon;
          return (
            <Glass
              key={p.title}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 28,
                padding: "30px 34px",
                opacity: Math.min(s, 1 - collapse),
                transform: `translateX(${(1 - s) * (i % 2 ? 700 : -700)}px) scale(${1 - collapse * 0.4}) rotate(${
                  (i % 2 ? 1 : -1) * 1.5
                }deg)`,
                border: `2px solid ${p.color}55`,
              }}
            >
              <Icon size={64} color={p.color} strokeWidth={2.2} />
              <div>
                <div style={{ fontSize: 40, fontWeight: 750 }}>{p.title}</div>
                <div style={{ fontSize: 28, color: C.muted, marginTop: 4 }}>{p.sub}</div>
              </div>
            </Glass>
          );
        })}
      </div>
      {frame >= end - 1 && (
        <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", top: -140 }}>
          <div
            style={{
              fontSize: 150,
              fontWeight: 900,
              letterSpacing: "-0.05em",
              transform: `scale(${2.4 - slam * 1.4})`,
              opacity: Math.min(1, slam * 1.5),
              textShadow: "0 0 50px rgba(83,109,254,0.8)",
              textAlign: "center",
              lineHeight: 0.95,
            }}
          >
            ISSO
            <br />
            ACABOU.
          </div>
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
};
