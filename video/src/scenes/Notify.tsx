import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { ArrowDown, ChevronRight } from "lucide-react";
import { C, FONT } from "../theme";
import { Logo, Notification, PrimaryButton, ramp, Tap, useIn, sp, Wordmark } from "../ui";
import type { SceneProps } from "../types";
import { wordAt } from "../types";

const PUSHES = [
  { word: "receba", title: "🎉 Parabéns! 100.000 views hoje", body: "312 posts postados hoje." },
  { word: "venda", title: "💸 Parabéns, Lucas! 50 vendas", body: "Pagas hoje." },
  { word: "meta", title: "Meta diária atingida", body: "Você alcançou 190.587 visualizações hoje (meta: 100.000)." },
  {
    word: "marco",
    title: "🌙 Resumo do seu dia",
    body: "Hoje: 12 conexões, 190.587 views, R$ 4.850,00 em vendas. Dormiu rico 😴💰",
  },
];

/** Notify: the phone lock screen filling with FlashPost pushes. */
export const Notify: React.FC<SceneProps> = ({ words }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const phone = useIn(0, 16);
  const ats = PUSHES.map((p, i) => wordAt(words, p.word, fps));
  return (
    <AbsoluteFill style={{ fontFamily: FONT, color: C.fg, alignItems: "center" }}>
      <div
        style={{
          position: "absolute",
          top: 150,
          width: 960,
          height: 1260,
          borderRadius: 90,
          border: "12px solid #23293b",
          overflow: "hidden",
          background:
            "radial-gradient(circle at 20% 10%, rgba(83,109,254,0.55), transparent 50%), radial-gradient(circle at 90% 80%, rgba(150,70,255,0.45), transparent 55%), #070a16",
          transform: `translateY(${(1 - phone) * 1300}px)`,
          boxShadow: "0 40px 100px rgba(0,0,0,0.6)",
        }}
      >
        <div style={{ textAlign: "center", marginTop: 70 }}>
          <div style={{ fontSize: 32, fontWeight: 600, color: "rgba(255,255,255,0.8)" }}>sexta-feira, 16 de outubro</div>
          <div style={{ fontSize: 190, fontWeight: 700, letterSpacing: "-0.04em", lineHeight: 1 }}>22:27</div>
        </div>
        <div style={{ position: "absolute", top: 400, left: 30, right: 30, display: "flex", flexDirection: "column-reverse", gap: 18 }}>
          {PUSHES.map((p, i) => {
            const s = sp(frame, fps, ats[i], 12, 170);
            if (frame < ats[i]) return null;
            return (
              <div
                key={p.title}
                style={{ opacity: s, transform: `translateY(${(1 - s) * -160}px) scale(${0.85 + s * 0.15})` }}
              >
                <Notification title={p.title} body={p.body} />
              </div>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};

/** CTA: stop posting by hand, tap the link. */
export const Cta: React.FC<SceneProps> = ({ words }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const brac = wordAt(words, "braço", fps);
  const coloque = wordAt(words, "Coloque", fps);
  const toque = wordAt(words, "Toque", fps);
  const agora = wordAt(words, "agora", fps);
  const l1 = useIn(0, 13);
  const strike = ramp(frame, brac, brac + 12);
  const out1 = ramp(frame, coloque - 6, coloque + 4);
  const logo = useIn(coloque, 13);
  const btn = useIn(toque - 4, 11, 160);
  const pulse = 1 + Math.max(0, Math.sin((frame - toque) / 5)) * 0.04 * (frame > toque ? 1 : 0);
  const arrow = Math.sin(frame / 4) * 14;
  return (
    <AbsoluteFill style={{ fontFamily: FONT, color: C.fg, alignItems: "center" }}>
      <div
        style={{
          position: "absolute",
          top: 520,
          fontSize: 104,
          fontWeight: 900,
          letterSpacing: "-0.04em",
          textAlign: "center",
          lineHeight: 1,
          opacity: l1 * (1 - out1),
          transform: `scale(${(0.6 + l1 * 0.4) * (1 - out1 * 0.3)})`,
        }}
      >
        Pare de postar
        <br />
        <span style={{ position: "relative", color: C.danger }}>
          no braço.
          <span
            style={{
              position: "absolute",
              left: -10,
              top: "52%",
              height: 12,
              width: `${strike * 105}%`,
              background: C.fg,
              borderRadius: 6,
            }}
          />
        </span>
      </div>
      {frame >= coloque - 2 && (
        <>
          <div style={{ position: "absolute", top: 230, filter: "drop-shadow(0 0 50px rgba(83,109,254,0.7))" }}>
            <Logo size={300} delay={coloque} />
          </div>
          <div style={{ position: "absolute", top: 580, transform: `scale(${logo})`, opacity: logo }}>
            <Wordmark size={120} />
          </div>
          <div
            style={{
              position: "absolute",
              top: 750,
              fontSize: 50,
              fontWeight: 700,
              textAlign: "center",
              opacity: logo,
              lineHeight: 1.2,
            }}
          >
            Seu Instagram no
            <br />
            <span style={{ color: C.neon, fontSize: 64, fontWeight: 900 }}>piloto automático.</span>
          </div>
        </>
      )}
      {frame >= toque - 6 && (
        <div style={{ position: "absolute", top: 1010, width: 820, transform: `scale(${btn * pulse})`, opacity: btn }}>
          <PrimaryButton style={{ height: 130, fontSize: 50, background: "linear-gradient(135deg,#5169f4,#22c1ee)" }}>
            Começar agora <ChevronRight size={52} strokeWidth={3} />
          </PrimaryButton>
          <div style={{ textAlign: "center", marginTop: 26, fontSize: 34, color: C.muted, fontWeight: 600 }}>
            flashpost.onrender.com
          </div>
          <div style={{ display: "flex", justifyContent: "center", marginTop: 6, transform: `translateY(${arrow}px)` }}>
            <ArrowDown size={70} color={C.neon} strokeWidth={3} />
          </div>
        </div>
      )}
      <Tap x={540} y={1075} at={agora} />
    </AbsoluteFill>
  );
};
