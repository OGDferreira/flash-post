import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/services/api";
import type { DailyViewsGoal } from "@/components/DailyViewsGoalCard";
import { useEffect, useState } from "react";
import { CalendarDays } from "lucide-react";

import { PeriodFilter, todayInput, type MetricsPeriod } from "@/features/analytics/period";
import { ConversionOverview } from "@/features/bots/ConversionOverview";

import { BotSalesPanel } from "@/features/bots/BotSalesPanel";
import { BotsListPanel } from "@/features/bots/BotsListPanel";
import { FlowsPanel } from "@/features/bots/FlowsPanel";
import { GatewaysPanel } from "@/features/bots/GatewaysPanel";
import { RemarketingPanel } from "@/features/bots/remarketing/RemarketingPanel";
import { SharedByMePanel } from "@/features/partners/SharedByMePanel";
import { SharedFlowsPanel } from "@/features/partners/SharedTemplates";

import { Navigate, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";

/** Each Falcon Bot section has its own address (the sidebar links to them). */
export const BOT_SECTIONS = {
  home: { slug: "", title: "Painel", eyebrow: "Visão geral", hint: "Leads, starts, vendas e conversão dos seus bots no período." },
  bots: { slug: "robos", title: "Meus bots", eyebrow: "Bots e leads", hint: "Conecte bots do Telegram e escolha o funil (ou a pasta de funis) de cada um." },
  flows: { slug: "funis", title: "Meus funis", eyebrow: "Funis", hint: "Funis criados por você: conteúdo, planos, entregas e o gateway de cada um." },
  remarketing: { slug: "remarketing", title: "Remarketing", eyebrow: "Bots e leads", hint: "Disparos para os leads de um funil, pelos próprios bots." },
  sharedByMe: { slug: "compartilhei", title: "Que compartilhei", eyebrow: "Funis", hint: "Seus funis compartilhados com cada sócio: gateway, a parte do vendedor, a sua comissão e as vendas. Só você altera essas regras." },
  shared: { slug: "compartilhados-comigo", title: "Compartilhados comigo", eyebrow: "Funis", hint: "Funis de outro proprietário que você pode usar nos seus bots. Gateway e comissão são definidos por quem compartilhou." },
  sales: { slug: "vendas", title: "Leads, starts e vendas", eyebrow: "Vendas e financeiro", hint: "Cada Pix gerado e pago, com taxas, comissões e o líquido de cada venda." },
  gateways: { slug: "gateways", title: "Gateways de pagamento", eyebrow: "Configuração", hint: "Configure os gateways dos seus funis próprios. Funis compartilhados com você usam o gateway de quem compartilhou." },
} as const;

type Tab = keyof typeof BOT_SECTIONS;
const tabBySlug = Object.fromEntries(Object.entries(BOT_SECTIONS).map(([id, { slug }]) => [slug, id as Tab])) as Record<string, Tab>;
export const botPath = (tab: Tab) => (BOT_SECTIONS[tab].slug ? `/bot/${BOT_SECTIONS[tab].slug}` : "/bot");

/** Old /feature/bots?tab=x links (notifications, bookmarks) open the new address. */
export function LegacyBotsRedirect() {
  const { search } = useLocation();
  const asked = new URLSearchParams(search).get("tab");
  return <Navigate replace to={asked && asked in BOT_SECTIONS ? botPath(asked as Tab) : "/bot"} />;
}

export function BotsPage() {
  const { section = "" } = useParams();
  const navigate = useNavigate();
  const tab: Tab | undefined = tabBySlug[section];
  // The flow editor has its own header and section navigation; give it the whole screen.
  const [editing, setEditing] = useState(false);
  const [params] = useSearchParams();
  const [remarketingFlow, setRemarketingFlow] = useState<string | null>(params.get("funil"));
  const [period, setPeriod] = useState<MetricsPeriod>({ period: "today", start: todayInput(), end: todayInput() });
  const goal = useQuery({
    queryKey: ["notifications", "goal", "me"],
    queryFn: () => apiRequest<DailyViewsGoal>("/api/notifications/goals/me"),
    staleTime: 60_000,
  });
  useEffect(() => {
    if (goal.data?.timezone) setPeriod((current) => current.period === "custom" ? current : {
      ...current, start: todayInput(goal.data.timezone), end: todayInput(goal.data.timezone),
    });
  }, [goal.data?.timezone]);
  if (!tab) return <Navigate replace to="/bot" />;
  const info = BOT_SECTIONS[tab];
  return (
    <div className="mx-auto w-full max-w-[1500px] space-y-4">
      {!editing && (
        <>
          {/* The Painel opens straight on the numbers, like SharkBot: the top bar already shows logo and name. */}
          {tab !== "home" && (
            <header className="flex flex-wrap items-end justify-between gap-3">
              <div className="min-w-0">
                <p className="text-xs font-medium uppercase tracking-[0.16em] text-accent">Falcon Bot · {info.eyebrow}</p>
                <h1 className="mt-2 flex items-center gap-2.5 text-2xl font-semibold text-fg sm:text-3xl">{info.title}</h1>
                <p className="mt-2 max-w-3xl text-sm text-muted">{info.hint}</p>
              </div>
            </header>
          )}
          {/* Each section is its own screen: the dashboard lives in "Painel", the robots in "Meus bots". */}
          {tab === "home" && <ConversionOverview onPeriod={setPeriod} period={period} />}
          {(tab === "flows" || tab === "bots") && (
            <div className="dashboard-card flex flex-wrap items-center justify-between gap-2 rounded-2xl px-4 py-3">
              <span className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.16em] text-muted">
                <CalendarDays size={14} /> Período
              </span>
              <PeriodFilter onChange={setPeriod} value={period} />
            </div>
          )}
        </>
      )}
      {tab === "bots" && <BotsListPanel period={period} />}
      {tab === "flows" && (
        <FlowsPanel
          onEditingChange={setEditing}
          onRemarketing={(flowId) => {
            navigate(`${botPath("remarketing")}?funil=${encodeURIComponent(flowId)}`);
            window.scrollTo({ top: 0, behavior: "smooth" });
          }}
          period={period}
        />
      )}
      {tab === "remarketing" && <RemarketingPanel flowId={remarketingFlow} onEditingChange={setEditing} onFlowChange={setRemarketingFlow} />}
      {tab === "shared" && <SharedFlowsPanel />}
      {tab === "sharedByMe" && <SharedByMePanel />}
      {tab === "sales" && <BotSalesPanel />}
      {tab === "gateways" && <GatewaysPanel />}
    </div>
  );
}
