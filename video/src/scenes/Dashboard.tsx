import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { Eye, Flame, Send, Target, Trophy, Users } from "lucide-react";
import { C, FONT } from "../theme";
import { Bar, Glass, Pill, ramp, useIn, fmt } from "../ui";
import type { SceneProps } from "../types";
import { wordAt } from "../types";

const Metric: React.FC<{
  icon: React.ElementType;
  title: string;
  value: string;
  detail: string;
  delay: number;
  accent?: string;
}> = ({ icon: Icon, title, value, detail, delay, accent = C.brandStrong }) => {
  const s = useIn(delay, 13);
  return (
    <Glass
      style={{
        padding: 28,
        flex: 1,
        opacity: s,
        transform: `translateY(${(1 - s) * 60}px) scale(${0.9 + s * 0.1})`,
      }}
    >
      <div
        style={{
          width: 64,
          height: 64,
          borderRadius: 20,
          background: `${accent}26`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <Icon size={36} color={accent} />
      </div>
      <div style={{ fontSize: 26, color: C.muted, marginTop: 18 }}>{title}</div>
      <div style={{ fontSize: 58, fontWeight: 800, letterSpacing: "-0.03em", fontVariantNumeric: "tabular-nums" }}>
        {value}
      </div>
      <div style={{ fontSize: 22, color: C.muted }}>{detail}</div>
    </Glass>
  );
};

/** Dashboard: views, posts, streak and record. */
export const Dashboard: React.FC<SceneProps> = ({ words }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const views = wordAt(words, "visualizações", fps);
  const posts = wordAt(words, "posts", fps);
  const seq = wordAt(words, "sequência", fps);
  const rec = wordAt(words, "recorde", fps);
  const all = wordAt(words, "Tudo", fps);
  const head = useIn(0, 15);
  const v = ramp(frame, views, views + 45, 0, 190587);
  const p = ramp(frame, posts, posts + 35, 0, 312);
  const goal = ramp(frame, all - 10, all + 30, 0, 1);
  const zoom = 1 + ramp(frame, all, all + 60, 0, 0.03);
  return (
    <AbsoluteFill style={{ fontFamily: FONT, color: C.fg, padding: "160px 60px 0", transform: `scale(${zoom})` }}>
      <div style={{ opacity: head, transform: `translateY(${(1 - head) * 40}px)` }}>
        <div style={{ fontSize: 56, fontWeight: 800, letterSpacing: "-0.03em" }}>Boa noite, Lucas 👋</div>
        <div style={{ fontSize: 26, color: C.muted, marginTop: 6 }}>Sexta-feira, 16 de outubro de 2026 às 22:27</div>
        <div style={{ display: "flex", gap: 12, marginTop: 24 }}>
          {["Hoje", "Ontem", "7 dias", "30 dias"].map((c, i) => (
            <Pill
              key={c}
              bg={i === 0 ? "linear-gradient(145deg,#5169f4,#3b52e0)" : "rgba(255,255,255,0.07)"}
              style={{ fontSize: 26, boxShadow: i === 0 ? "0 8px 22px rgba(83,109,254,0.38)" : "none" }}
            >
              {c}
            </Pill>
          ))}
        </div>
      </div>
      <div style={{ display: "flex", gap: 20, marginTop: 30 }}>
        <Metric icon={Eye} title="Visualizações" value={fmt(v)} detail="Insights da Meta" delay={views - 6} accent={C.neon} />
        <Metric icon={Send} title="Posts no período" value={fmt(p)} detail="Publicados pelo FlashPost" delay={posts - 6} />
      </div>
      <div style={{ display: "flex", gap: 20, marginTop: 20 }}>
        <Metric
          icon={Flame}
          title="Sequência"
          value={`${Math.round(ramp(frame, seq, seq + 20, 0, 12))} dias`}
          detail="meta de hoje batida ✅"
          delay={seq - 6}
          accent="#f2d48a"
        />
        <Metric
          icon={Trophy}
          title="Recorde pessoal"
          value="25"
          detail="🏆 novo recorde hoje!"
          delay={rec - 6}
          accent="#f2d48a"
        />
      </div>
      <Glass style={{ marginTop: 20, padding: 30, opacity: useIn(all - 12, 14) }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14, fontSize: 30, fontWeight: 750 }}>
          <Target size={36} color={C.neon} /> Meta diária de visualizações
          <div style={{ flex: 1 }} />
          <Users size={30} color={C.muted} />
          <span style={{ fontSize: 24, color: C.muted, fontWeight: 500 }}>12 contas</span>
        </div>
        <div style={{ fontSize: 44, fontWeight: 800, marginTop: 14, fontVariantNumeric: "tabular-nums" }}>
          {fmt(goal * 190587)} <span style={{ color: C.muted, fontSize: 32 }}>/ 100.000</span>
        </div>
        <Bar p={goal * 1.9} h={20} style={{ marginTop: 14 }} />
        <div style={{ fontSize: 24, color: "#7ee2bd", marginTop: 12, opacity: goal > 0.55 ? 1 : 0 }}>
          Meta atingida hoje — notificação enviada.
        </div>
      </Glass>
    </AbsoluteFill>
  );
};
