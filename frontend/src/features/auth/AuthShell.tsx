import type { ReactNode } from "react";
import { BadgeDollarSign, Target, Wallet } from "lucide-react";
import { Link } from "react-router-dom";

import { BrandLogo } from "@/components/BrandLogo";

const copy = {
  login: {
    eyebrow: "Bem-vindo de volta",
    title: ["Cada conexão vira", "dinheiro no bolso."],
    text: "Veja quanto você já ganhou hoje, o que falta receber e quanto ainda pode alcançar no mês — tudo em um painel só.",
  },
  register: {
    eyebrow: "Comece agora",
    title: ["Transforme suas contas em", "receita previsível."],
    text: "Gerencie vários perfis do Instagram, acompanhe a produção da equipe e saiba exatamente quanto cada conta conectada rende.",
  },
} as const;

const benefits = [
  { icon: BadgeDollarSign, title: "Ganhos do dia", text: "Valor a receber calculado por conta conectada." },
  { icon: Target, title: "Metas e bônus", text: "Meta diária, mensal e ranking da equipe." },
  { icon: Wallet, title: "Pagamentos claros", text: "O que foi pago e o que ainda falta pagar." },
];

export function AuthShell({ mode, children }: { mode: "login" | "register"; children: ReactNode }) {
  const c = copy[mode];
  return (
    <main className="relative grid min-h-svh place-items-center overflow-x-hidden bg-transparent px-4 py-4 sm:px-5 sm:py-10">
      <div className="glass-panel relative grid w-full max-w-[1040px] overflow-hidden !rounded-3xl md:grid-cols-[1.1fr_0.9fr]">
        <section className="relative flex flex-col gap-8 p-5 sm:p-8 md:min-h-[600px] md:p-10">
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -left-24 -top-24 size-72 rounded-full opacity-40 blur-3xl"
            style={{ background: "radial-gradient(circle, rgb(var(--brand-rgb) / 0.55), transparent 70%)" }}
          />
          <Link to="/" className="relative flex w-fit items-center gap-3">
            <BrandLogo className="size-10" />
            <span className="text-base font-semibold tracking-[-0.03em] text-fg">FlashPost</span>
          </Link>
          <div className="relative max-w-md md:my-auto">
            <p className="mb-4 inline-flex rounded-full border border-line bg-brand-soft px-3 py-1 text-xs font-medium text-accent">
              {c.eyebrow}
            </p>
            <h1 className="text-[2rem] font-semibold leading-[1.08] tracking-[-0.05em] text-fg sm:text-5xl">
              {c.title[0]}
              <br />
              <span className="text-accent">{c.title[1]}</span>
            </h1>
            <p className="mt-4 text-sm leading-6 text-muted sm:text-base sm:leading-7">{c.text}</p>
            <ul className="mt-6 hidden gap-3 sm:grid">
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
          <div className="relative hidden items-center justify-between rounded-2xl border border-line-soft bg-surface-inset/60 px-4 py-3 md:flex">
            <div>
              <p className="text-[11px] text-muted">A receber hoje</p>
              <p className="text-xl font-semibold tracking-[-0.03em] text-fg">R$ 245,00</p>
            </div>
            <p className="text-right text-[11px] text-muted">
              70 conexões
              <span className="block">exemplo ilustrativo</span>
            </p>
          </div>
        </section>
        {children}
      </div>
    </main>
  );
}
