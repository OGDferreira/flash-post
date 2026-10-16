import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { CheckCircle2, Infinity as InfinityIcon, Timer, UploadCloud } from "lucide-react";
import { C, FONT } from "../theme";
import { Eyebrow, Glass, Pill, PrimaryButton, ramp, Tap, Thumb, Title, useIn, fmt } from "../ui";
import type { SceneProps } from "../types";
import { wordAt } from "../types";

const Field: React.FC<{ label: string; value: string; delay: number; hi?: boolean }> = ({ label, value, delay, hi }) => {
  const s = useIn(delay, 14);
  return (
    <div style={{ opacity: s, transform: `translateY(${(1 - s) * 30}px)`, flex: 1 }}>
      <div style={{ fontSize: 24, color: C.muted, marginBottom: 10 }}>{label}</div>
      <div
        style={{
          padding: "20px 24px",
          borderRadius: 20,
          background: "rgba(255,255,255,0.06)",
          border: `2px solid ${hi ? C.neon : "rgba(255,255,255,0.12)"}`,
          fontSize: 34,
          fontWeight: 700,
        }}
      >
        {value}
      </div>
    </div>
  );
};

const ACCOUNTS = ["@cortes.humor", "@rindo.alto", "@noticias.dia", "@vida.leve", "@memes.br"];
const STATUSES = [
  { t: "Publicando agora", c: C.brandStrong },
  { t: "Aguardando intervalo", c: C.muted },
  { t: "Na fila", c: "#f2d48a" },
  { t: "Publicado", c: "#7ee2bd" },
];

/** Loop: bulk upload, interval settings, and the loop running across accounts. */
export const Loop: React.FC<SceneProps> = ({ words }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const crie = wordAt(words, "crie", fps);
  const click = wordAt(words, "FlashPost", fps);
  const run = wordAt(words, "publica", fps);
  const interval = wordAt(words, "intervalo", fps);
  const head = useIn(0, 15);
  const gridOut = ramp(frame, crie - 6, crie + 4);
  const formIn = ramp(frame, crie - 2, crie + 10);
  const formOut = ramp(frame, run - 6, run + 4);
  const cardIn = useIn(run - 2, 14);
  const uploaded = Math.min(40, Math.round(ramp(frame, 4, crie - 10, 0, 40)));
  const published = Math.floor(Math.max(0, frame - run) / 9);
  const hiInterval = frame >= interval && frame < interval + 40;
  return (
    <AbsoluteFill style={{ fontFamily: FONT, color: C.fg, padding: "170px 70px 0" }}>
      <div style={{ opacity: head, display: "flex", alignItems: "flex-end", justifyContent: "space-between" }}>
        <div>
          <Eyebrow>Publicação automatizada</Eyebrow>
          <Title style={{ marginTop: 10, display: "flex", alignItems: "center", gap: 18 }}>
            <InfinityIcon size={70} color={C.neon} style={{ transform: `rotate(${frame * (frame > run ? 4 : 0)}deg)` }} />
            Loops
          </Title>
        </div>
      </div>

      {/* phase A: bulk upload */}
      <div style={{ position: "absolute", top: 380, left: 70, right: 70, opacity: 1 - gridOut, transform: `scale(${1 - gridOut * 0.1})` }}>
        <Glass style={{ padding: 30 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 16, fontSize: 34, fontWeight: 700 }}>
            <UploadCloud size={44} color={C.neon} />
            Mídias do loop ({uploaded})
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 14, marginTop: 24 }}>
            {Array.from({ length: 20 }).map((_, i) => {
              const s = useIn(4 + i * 1.6, 12, 180);
              return (
                <div key={i} style={{ transform: `scale(${s})`, opacity: s }}>
                  <Thumb i={i} w={160} h={250} />
                </div>
              );
            })}
          </div>
        </Glass>
      </div>

      {/* phase B: loop settings */}
      {frame >= crie - 4 && frame < run + 6 && (
        <div style={{ position: "absolute", top: 380, left: 70, right: 70, opacity: formIn * (1 - formOut) }}>
          <Glass style={{ padding: 36, display: "flex", flexDirection: "column", gap: 26 }}>
            <div style={{ fontSize: 36, fontWeight: 750 }}>Configurações do loop</div>
            <Field label="Nome do loop" value="Reels diários" delay={crie} />
            <div style={{ display: "flex", gap: 22 }}>
              <Field label="Intervalo mínimo (min)" value="20" delay={crie + 4} hi />
              <Field label="Intervalo máximo (min)" value="40" delay={crie + 7} hi />
            </div>
            <div style={{ display: "flex", gap: 22 }}>
              <Field label="Máx. por conta/dia" value="24" delay={crie + 10} />
              <Field label="Tipo de publicação" value="Reels (vídeo)" delay={crie + 12} />
            </div>
            <PrimaryButton style={{ marginTop: 8, transform: `scale(${frame >= click && frame < click + 6 ? 0.95 : 1})` }}>
              Criar loop
            </PrimaryButton>
          </Glass>
          <Tap x={470} y={585} at={click} />
        </div>
      )}

      {/* phase C: the loop running */}
      {frame >= run - 4 && (
        <div style={{ position: "absolute", top: 380, left: 70, right: 70, opacity: cardIn, transform: `translateY(${(1 - cardIn) * 80}px)` }}>
          <Glass style={{ padding: 34 }} glow="rgba(83,109,254,0.25)">
            <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
              <div style={{ fontSize: 44, fontWeight: 800 }}>Reels diários</div>
              <Pill bg="rgba(126,226,189,0.15)" color="#7ee2bd" style={{ fontSize: 24, padding: "6px 16px" }}>
                ● ativo
              </Pill>
              <Pill style={{ fontSize: 24, padding: "6px 16px" }}>Contínuo</Pill>
            </div>
            <div
              style={{
                marginTop: 18,
                fontSize: 29,
                display: "flex",
                alignItems: "center",
                gap: 10,
                padding: "12px 16px",
                borderRadius: 16,
                color: hiInterval ? C.fg : C.muted,
                background: hiInterval ? "rgba(0,201,216,0.16)" : "transparent",
                boxShadow: hiInterval ? `0 0 0 2px ${C.neon}` : "none",
              }}
            >
              <Timer size={32} /> 20–40 min entre posts · até 24/dia por conta · Reels
            </div>
            <div style={{ marginTop: 10, fontSize: 28, color: "#7ee2bd" }}>
              5 contas ativas no loop · 40 vídeos no loop
            </div>
            <div style={{ marginTop: 26, display: "flex", flexDirection: "column", gap: 14 }}>
              {ACCOUNTS.map((a, i) => {
                const st = STATUSES[(Math.floor(Math.max(0, frame - run) / 22) + i) % STATUSES.length];
                const rs = useIn(run + 4 + i * 4, 14);
                return (
                  <div
                    key={a}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      padding: "18px 22px",
                      borderRadius: 18,
                      background: "rgba(255,255,255,0.05)",
                      opacity: rs,
                      transform: `translateX(${(1 - rs) * 120}px)`,
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 16, fontSize: 30, fontWeight: 650 }}>
                      <Thumb i={i + 3} w={56} h={56} />
                      {a}
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 26, fontWeight: 650, color: st.c }}>
                      {st.t === "Publicado" && <CheckCircle2 size={28} />}
                      {st.t === "Publicando agora" && (
                        <span
                          style={{
                            width: 14,
                            height: 14,
                            borderRadius: 7,
                            background: st.c,
                            opacity: 0.5 + 0.5 * Math.sin(frame / 3),
                          }}
                        />
                      )}
                      {st.t}
                    </div>
                  </div>
                );
              })}
            </div>
            <div style={{ marginTop: 24, display: "flex", justifyContent: "space-between", fontSize: 28, color: C.muted }}>
              <span>Próxima execução: 16/10, 22:47</span>
              <span style={{ color: C.fg, fontWeight: 750 }}>{fmt(published + 112)} publicados hoje</span>
            </div>
          </Glass>
        </div>
      )}
    </AbsoluteFill>
  );
};
