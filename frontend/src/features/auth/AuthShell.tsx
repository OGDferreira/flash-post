import { useEffect, useState, type ReactNode } from "react";
import { CalendarClock, ChartNoAxesColumn, Link2, Workflow } from "lucide-react";
import { Link } from "react-router-dom";

import { BrandLogo, BrandLockup } from "@/components/BrandLogo";

const copy = {
  login: {
    eyebrow: "Bem-vindo de volta",
    title: ["Seu Instagram no", "piloto automático."],
    text: "Conecte suas contas, agende publicações e crie automações — para você ou para sua empresa.",
  },
  register: {
    eyebrow: "Comece agora",
    title: ["Menos trabalho manual,", "mais resultado."],
    text: "O Falcon Post conecta seus perfis, publica no horário certo e automatiza a rotina da sua equipe.",
  },
} as const;

const phrases = [
  "Agende uma semana de posts em minutos. 🗓️",
  "Automações para criadores, agências e empresas. ⚙️",
  "Vários perfis do Instagram, um só painel. 📱",
  "Seus posts saem no horário certo, até enquanto você dorme. 😴",
  "Sua equipe produz, você acompanha tudo em tempo real. 👀",
  "Métricas reais direto da Meta, sem planilha. 📊",
  "O facilitador que sua empresa estava procurando. 🚀",
];

const benefits = [
  { icon: Link2, title: "Conecte suas contas", text: "Vários perfis do Instagram no mesmo lugar." },
  { icon: CalendarClock, title: "Agenda de publicações", text: "Programe posts e deixe publicar sozinho." },
  { icon: Workflow, title: "Automações", text: "Rotinas automáticas para pessoas e empresas." },
  { icon: ChartNoAxesColumn, title: "Métricas e equipe", text: "Visualizações, metas e produção do time." },
];

function RotatingPhrase() {
  const [index, setIndex] = useState(0);
  useEffect(() => {
    const id = window.setInterval(() => setIndex((value) => (value + 1) % phrases.length), 3500);
    return () => window.clearInterval(id);
  }, []);
  return (
    <p aria-live="polite" className="mt-3 min-h-5 text-xs font-medium text-accent sm:text-sm">
      <span className="page-enter inline-block" key={index}>
        {phrases[index]}
      </span>
    </p>
  );
}

export function AuthShell({ mode, children }: { mode: "login" | "register"; children: ReactNode }) {
  const c = copy[mode];
  return (
    <main className="relative grid min-h-svh place-items-center overflow-x-hidden bg-transparent px-3 py-3 sm:px-5 sm:py-10">
      <div className="glass-panel relative grid w-full max-w-[1040px] overflow-hidden !rounded-3xl md:grid-cols-[1.1fr_0.9fr]">
        <section className="relative flex flex-col gap-3 p-4 sm:gap-8 sm:p-8 md:min-h-[600px] md:p-10">
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -left-24 -top-24 size-72 rounded-full opacity-40 blur-3xl"
            style={{ background: "radial-gradient(circle, rgb(var(--brand-rgb) / 0.55), transparent 70%)" }}
          />
          <Link to="/" className="relative flex w-fit items-center gap-2.5">
            <BrandLogo animated className="size-9 sm:size-11" />
            <BrandLockup app="post" className="h-4 sm:h-5" kind="wordmark" />
            <span aria-hidden="true" className="text-muted">+</span>
            <BrandLogo app="bot" className="size-7 sm:size-8" />
          </Link>
          <div className="relative max-w-md md:my-auto">
            <p className="mb-2 inline-flex rounded-full border border-line bg-brand-soft px-2.5 py-0.5 text-[11px] font-medium text-accent sm:mb-4 sm:px-3 sm:py-1 sm:text-xs">
              {c.eyebrow}
            </p>
            <h1 className="text-[1.6rem] font-semibold leading-[1.1] tracking-[-0.045em] text-fg sm:text-5xl sm:leading-[1.08]">
              {c.title[0]}
              <br />
              <span className="text-accent">{c.title[1]}</span>
            </h1>
            <p className="mt-2 text-[13px] leading-5 text-muted sm:mt-4 sm:text-base sm:leading-7">{c.text}</p>
            <RotatingPhrase />
            <ul className="mt-6 hidden gap-3 md:grid">
              {benefits.map(({ icon: Icon, title, text }) => (
                <li className="flex items-start gap-3" key={title}>
                  <span className="grid size-9 shrink-0 place-items-center rounded-xl border border-line-soft bg-brand-soft text-accent">
                    <Icon size={17} />
                  </span>
                  <span className="text-sm">
                    <strong className="font-semibold text-fg">{title}</strong>
                    <span className="block text-muted">{text}</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </section>
        {children}
      </div>
    </main>
  );
}
