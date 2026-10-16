import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { Folder, Sparkles } from "lucide-react";
import { C, FONT } from "../theme";
import { Avatar, Glass, Logo, ramp, useIn, sp, Wordmark, Eyebrow, Title, Pill } from "../ui";
import type { SceneProps } from "../types";
import { wordAt } from "../types";

/** Reveal: the logo slams in on the beat drop. */
export const Reveal: React.FC<SceneProps> = ({ words }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const at = wordAt(words, "FlashPost", fps);
  const word = useIn(at + 4, 13);
  const tag = useIn(at + 16, 14);
  const flash = ramp(frame, at, at + 10, 1, 0);
  const ring = ramp(frame, at, at + 30);
  const pre = useIn(0, 14);
  return (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", fontFamily: FONT, color: C.fg }}>
      <div
        style={{
          position: "absolute",
          top: 330,
          fontSize: 48,
          fontWeight: 650,
          color: C.muted,
          opacity: pre * (frame < at ? 1 : 0.6),
          transform: `translateY(${(1 - pre) * 40}px)`,
        }}
      >
        Conheça o
      </div>
      {/* light rays */}
      <div
        style={{
          position: "absolute",
          width: 1600,
          height: 1600,
          top: 160,
          background: `conic-gradient(from ${frame * 0.6}deg, transparent 0deg, rgba(83,109,254,0.18) 20deg, transparent 40deg, transparent 90deg, rgba(0,201,216,0.14) 110deg, transparent 130deg, transparent 180deg, rgba(83,109,254,0.18) 200deg, transparent 220deg, transparent 270deg, rgba(0,201,216,0.14) 290deg, transparent 310deg)`,
          borderRadius: "50%",
          opacity: frame >= at ? 1 : 0,
          maskImage: "radial-gradient(circle, black 20%, transparent 65%)",
        }}
      />
      <div
        style={{
          position: "absolute",
          top: 520,
          width: 340,
          height: 340,
          borderRadius: "50%",
          border: "6px solid rgba(107,129,255,0.8)",
          transform: `scale(${1 + ring * 2.2})`,
          opacity: frame >= at ? 1 - ring : 0,
        }}
      />
      <div style={{ position: "absolute", top: 480, filter: "drop-shadow(0 0 60px rgba(83,109,254,0.7))" }}>
        {frame >= at - 2 && <Logo size={420} delay={at - 2} />}
      </div>
      <div
        style={{
          position: "absolute",
          top: 960,
          transform: `scale(${word})`,
          opacity: word,
        }}
      >
        <Wordmark size={150} />
      </div>
      <div
        style={{
          position: "absolute",
          top: 1150,
          fontSize: 46,
          fontWeight: 600,
          color: C.fg,
          opacity: tag,
          transform: `translateY(${(1 - tag) * 30}px)`,
          textAlign: "center",
        }}
      >
        Seu Instagram no <span style={{ color: C.neon, fontWeight: 800 }}>piloto automático.</span>
      </div>
      <AbsoluteFill style={{ background: "#fff", opacity: frame >= at ? flash * 0.7 : 0 }} />
    </AbsoluteFill>
  );
};

const FOLDERS = [
  { name: "Humor", color: "#00c9d8", base: 14, accounts: ["@cortes.humor", "@rindo.alto", "@memes.br"] },
  { name: "Notícias", color: "#536dfe", base: 9, accounts: ["@noticias.dia", "@urgente.br"] },
  { name: "Lifestyle", color: "#b171ff", base: 11, accounts: ["@vida.leve", "@rotina.fit"] },
];

/** Folders: connected accounts flying into colored folders. */
export const Folders: React.FC<SceneProps> = ({ words }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const head = useIn(0, 15);
  const org = wordAt(words, "organize", fps);
  const connect = wordAt(words, "contas", fps);
  const active = Math.round(ramp(frame, 6, connect + 20, 0, 48));
  let k = 0;
  return (
    <AbsoluteFill style={{ fontFamily: FONT, color: C.fg, padding: "170px 70px 0" }}>
      <div style={{ opacity: head, transform: `translateY(${(1 - head) * 40}px)` }}>
        <Eyebrow>Organização</Eyebrow>
        <Title style={{ marginTop: 10 }}>Pastas de perfis</Title>
      </div>
      <Glass
        style={{
          marginTop: 36,
          padding: "28px 34px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          opacity: head,
        }}
      >
        <div>
          <div style={{ fontSize: 28, color: C.muted }}>Contas ativas</div>
          <div style={{ fontSize: 76, fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>{active}</div>
          <div style={{ fontSize: 24, color: "#7ee2bd" }}>Com autorização válida</div>
        </div>
        <div style={{ display: "flex" }}>
          {["L", "A", "M", "R", "J"].map((n, i) => {
            const s = sp(frame, fps, 4 + i * 5, 12);
            return (
              <div key={n} style={{ marginLeft: i ? -26 : 0, transform: `scale(${s})` }}>
                <Avatar name={n} size={84} hue={200 + i * 30} />
              </div>
            );
          })}
        </div>
      </Glass>
      <div style={{ marginTop: 30, display: "flex", flexDirection: "column", gap: 26 }}>
        {FOLDERS.map((f, fi) => {
          const s = sp(frame, fps, org - 14 + fi * 6, 14);
          return (
            <Glass
              key={f.name}
              style={{
                padding: "28px 32px",
                border: `2px solid ${f.color}55`,
                opacity: s,
                transform: `translateX(${(1 - s) * 400}px)`,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
                <Folder size={44} color={f.color} fill={`${f.color}33`} />
                <div style={{ fontSize: 42, fontWeight: 750 }}>{f.name}</div>
                <div style={{ fontSize: 30, color: C.muted }}>
                  ({f.base + Math.round(ramp(frame, org, org + 40, 0, f.accounts.length))} contas)
                </div>
                <div style={{ flex: 1 }} />
                <Pill bg={`${f.color}22`} color={f.color} style={{ fontSize: 22, padding: "8px 16px" }}>
                  <Sparkles size={22} /> Auto por nome
                </Pill>
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginTop: 20 }}>
                {f.accounts.map((a) => {
                  const at = org + 4 + k++ * 7;
                  const c = sp(frame, fps, at, 12, 160);
                  return (
                    <div
                      key={a}
                      style={{
                        padding: "10px 20px",
                        borderRadius: 999,
                        background: "rgba(255,255,255,0.07)",
                        border: `1.5px solid ${f.color}66`,
                        fontSize: 26,
                        fontWeight: 600,
                        opacity: c,
                        transform: `translateY(${(1 - c) * -260}px) scale(${0.6 + c * 0.4})`,
                      }}
                    >
                      {a}
                    </div>
                  );
                })}
              </div>
            </Glass>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
