import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { Medal, UserPlus } from "lucide-react";
import { C, FONT } from "../theme";
import { Avatar, Bar, Eyebrow, Glass, Notification, Pill, ramp, Title, useIn, clamp } from "../ui";
import type { SceneProps } from "../types";
import { wordAt } from "../types";

const TEAM = [
  { name: "Lucas", nick: "@lucas", hue: 228, a: 22, b: 24 },
  { name: "Ana", nick: "@ana", hue: 320, a: 18, b: 27 },
  { name: "Marcos", nick: "@marcos", hue: 160, a: 15, b: 17 },
  { name: "Rafa", nick: "@rafa", hue: 30, a: 11, b: 14 },
];
const ROW = 118;

/** Team: create collaborators, set goals and pay, watch the ranking. */
export const Team: React.FC<SceneProps> = ({ words }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const cad = wordAt(words, "Cadastre", fps);
  const defina = wordAt(words, "defina", fps);
  const ranking = wordAt(words, "acompanhe", fps);
  const pass = wordAt(words, "ranking", fps);
  const head = useIn(0, 15);
  const form = useIn(cad - 4, 14);
  const formOut = ramp(frame, ranking - 6, ranking + 6);
  const board = useIn(ranking - 2, 14);
  const swap = ramp(frame, pass - 10, pass + 8);
  const toast = useIn(pass + 8, 12, 160);
  const counts = TEAM.map((m) => interpolate(swap, [0, 1], [m.a, m.b], clamp));
  const rank = (key: "a" | "b") => {
    const sorted = [...TEAM.keys()].sort((x, y) => TEAM[y][key] - TEAM[x][key]);
    return TEAM.map((_, i) => sorted.indexOf(i));
  };
  const r0 = rank("a");
  const r1 = rank("b");
  const max = 30;
  return (
    <AbsoluteFill style={{ fontFamily: FONT, color: C.fg, padding: "170px 70px 0" }}>
      <div style={{ opacity: head }}>
        <Eyebrow>Equipe</Eyebrow>
        <Title style={{ marginTop: 10 }}>{frame < ranking ? "Colaboradores" : "Ranking de conexões"}</Title>
      </div>

      {frame < ranking + 8 && (
        <Glass
          style={{
            position: "absolute",
            top: 400,
            left: 70,
            right: 70,
            padding: 34,
            opacity: form * (1 - formOut),
            transform: `translateY(${(1 - form) * 80}px)`,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 16, fontSize: 36, fontWeight: 750 }}>
            <UserPlus size={42} color={C.neon} /> Criar acesso de colaborador
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 22, marginTop: 28 }}>
            <Avatar name="Ana" size={100} hue={320} />
            <div>
              <div style={{ fontSize: 38, fontWeight: 750 }}>Ana Souza</div>
              <div style={{ fontSize: 26, color: C.muted }}>@ana · ana@equipe.com</div>
            </div>
            <div style={{ flex: 1 }} />
            <Pill bg="rgba(126,226,189,0.15)" color="#7ee2bd" style={{ fontSize: 22 }}>
              Acesso liberado
            </Pill>
          </div>
          {[
            ["Valor por conexão", "R$ 5,00"],
            ["Meta diária de conexões", "10"],
            ["Meta mensal de conexões", "30"],
            ["Bônus ao cumprir meta mensal", "R$ 150,00"],
          ].map(([l, v], i) => {
            const s = useIn(defina - 4 + i * 5, 14);
            return (
              <div
                key={l}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  padding: "22px 0",
                  borderTop: "1px solid rgba(255,255,255,0.08)",
                  marginTop: i ? 0 : 24,
                  fontSize: 30,
                  opacity: s,
                  transform: `translateX(${(1 - s) * 60}px)`,
                }}
              >
                <span style={{ color: C.muted }}>{l}</span>
                <span style={{ fontWeight: 800 }}>{v}</span>
              </div>
            );
          })}
          <div style={{ marginTop: 12, fontSize: 26, color: C.muted }}>Meta mensal · 18 / 30 contas · 60%</div>
          <Bar p={0.6 * ramp(frame, defina, defina + 30)} grad="linear-gradient(90deg,#d69b44,#f2d48a)" style={{ marginTop: 12 }} />
        </Glass>
      )}

      {frame >= ranking - 4 && (
        <Glass
          style={{
            position: "absolute",
            top: 400,
            left: 70,
            right: 70,
            padding: 34,
            opacity: board,
            transform: `translateY(${(1 - board) * 80}px)`,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <Medal size={40} color="#f2d48a" />
            <div style={{ fontSize: 34, fontWeight: 750 }}>Produção de hoje</div>
            <div style={{ flex: 1 }} />
            <Pill bg="linear-gradient(145deg,#5169f4,#3b52e0)" style={{ fontSize: 24 }}>
              Dia
            </Pill>
            <Pill style={{ fontSize: 24 }}>Mensal</Pill>
          </div>
          <div style={{ position: "relative", height: ROW * TEAM.length, marginTop: 24 }}>
            {TEAM.map((m, i) => {
              const pos = swap > 0.5 ? r1[i] : r0[i];
              const y = interpolate(swap, [0, 1], [r0[i], r1[i]]) * ROW;
              const rs = useIn(ranking + i * 4, 14);
              return (
                <div
                  key={m.name}
                  style={{
                    position: "absolute",
                    left: 0,
                    right: 0,
                    top: y,
                    zIndex: i === 1 ? 2 : 1,
                    display: "flex",
                    alignItems: "center",
                    gap: 20,
                    opacity: rs,
                    transition: "none",
                  }}
                >
                  <div style={{ width: 56, fontSize: 32, fontWeight: 800, color: pos === 0 ? "#f2d48a" : C.muted }}>
                    #{pos + 1}
                  </div>
                  <Avatar name={m.name} size={76} hue={m.hue} />
                  <div style={{ flex: 1 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 30, fontWeight: 700 }}>
                      <span>
                        {m.name} <span style={{ color: C.muted, fontWeight: 500, fontSize: 24 }}>{m.nick}</span>
                      </span>
                      <span style={{ fontVariantNumeric: "tabular-nums" }}>{Math.round(counts[i])} contas</span>
                    </div>
                    <Bar
                      p={(counts[i] / max) * rs}
                      h={12}
                      grad={i === 1 ? "linear-gradient(90deg,#536dfe,#b171ff)" : "#6b81ff"}
                      style={{ marginTop: 10 }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </Glass>
      )}

      <div
        style={{
          position: "absolute",
          top: 1000,
          left: 50,
          right: 50,
          opacity: toast,
          transform: `translateY(${(1 - toast) * -120}px)`,
        }}
      >
        <Notification title="⚠️ Ana te passou no ranking do dia" body="Vai deixar? 😤" />
      </div>
    </AbsoluteFill>
  );
};
