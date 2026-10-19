import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Bot, CalendarDays, GitBranch, Megaphone, Receipt, Share2 } from "lucide-react";

import { FlashBotLogo } from "@/components/FlashBotLogo";
import { PeriodFilter, todayInput, type MetricsPeriod } from "@/features/analytics/period";
import { ConversionOverview } from "@/features/bots/ConversionOverview";

import { BotSalesPanel } from "@/features/bots/BotSalesPanel";
import { BotsListPanel } from "@/features/bots/BotsListPanel";
import { FlowsPanel } from "@/features/bots/FlowsPanel";
import { RemarketingPanel } from "@/features/bots/remarketing/RemarketingPanel";
import { SharedFlowsPanel } from "@/features/partners/SharedTemplates";

const tabs = [
  { id: "bots", label: "Meus bots", short: "Robôs", Icon: Bot },
  { id: "flows", label: "Meus funis", short: "Funis", Icon: GitBranch },
  { id: "remarketing", label: "Remarketing", short: "Remarketing", Icon: Megaphone },
  { id: "shared", label: "Funis compartilhados", short: "Compartilhados", Icon: Share2 },
  { id: "sales", label: "Vendas", short: "Vendas", Icon: Receipt },
] as const;

type Tab = (typeof tabs)[number]["id"];

/** Floating tab bar: stuck under the header on desktop; on phones it lives at the bottom of the
 * screen like an app (rendered on <body> so no animated ancestor can unpin it). */
function TabBar({ tab, onChoose }: { tab: Tab; onChoose: (tab: Tab) => void }) {
  const buttons = (desktop: boolean) =>
    tabs.map(({ id, label, short, Icon }) => (
      <button
        aria-selected={tab === id}
        className={`flex min-w-0 items-center justify-center rounded-full font-medium transition-colors ${
          desktop ? "min-h-10 gap-2 px-4 text-sm" : "min-h-12 flex-col gap-0.5 rounded-xl px-1 text-[10px]"
        } ${tab === id ? "bg-brand text-white shadow" : "text-muted hover:text-fg"}`}
        key={id}
        onClick={() => onChoose(id)}
        role="tab"
        type="button"
      >
        <Icon className="shrink-0" size={desktop ? 16 : 18} />
        <span className="max-w-full truncate">{desktop ? label : short}</span>
      </button>
    ));
  return (
    <>
      <nav
        aria-label="Seções do FlashBot"
        className="sticky top-[calc(72px+env(safe-area-inset-top)+10px)] z-20 mx-auto hidden w-fit lg:block"
      >
        <div className="flex gap-1 rounded-full border border-line bg-[var(--nm-bg)]/95 p-1 shadow-2xl backdrop-blur" role="tablist">
          {buttons(true)}
        </div>
      </nav>
      {createPortal(
        <nav
          aria-label="Seções do FlashBot no celular"
          className="fixed inset-x-3 bottom-[calc(env(safe-area-inset-bottom)+92px)] z-30 lg:hidden"
        >
          <div className="grid grid-cols-5 gap-0.5 rounded-2xl border border-line bg-[var(--nm-bg)]/95 p-1 shadow-2xl backdrop-blur" role="tablist">
            {buttons(false)}
          </div>
        </nav>,
        document.body,
      )}
    </>
  );
}

export function BotsPage() {
  const [tab, setTab] = useState<Tab>("bots");
  // The flow editor has its own header and section navigation; give it the whole screen.
  const [editing, setEditing] = useState(false);
  const [remarketingFlow, setRemarketingFlow] = useState<string | null>(null);
  const [period, setPeriod] = useState<MetricsPeriod>({ period: "30d", start: todayInput(), end: todayInput() });
  // On phones the tab bar sits at the bottom like an app; the floating refresh button steps aside.
  useEffect(() => {
    if (editing) return;
    document.body.dataset.bottomTabs = "1";
    return () => {
      delete document.body.dataset.bottomTabs;
    };
  }, [editing]);
  const choose = (next: Tab) => {
    setTab(next);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  return (
    <div className={`mx-auto w-full max-w-[1500px] space-y-4 ${editing ? "" : "pb-24 lg:pb-0"}`}>
      {!editing && (
        <>
          <header>
            <p className="text-xs font-medium uppercase tracking-[0.16em] text-accent">Vendas</p>
            <h1 className="mt-2 flex items-center gap-2.5 text-2xl font-semibold text-fg sm:text-3xl">
              <FlashBotLogo className="size-8 shrink-0 sm:size-9" />
              FlashBot
            </h1>
            <p className="mt-2 text-sm text-muted">
              Seus robôs de venda no Telegram: conecte, monte o funil de cada um e acompanhe as vendas no Pix em tempo real.
            </p>
          </header>
          <TabBar onChoose={choose} tab={tab} />
          {/* Each tab is its own screen: the dashboard belongs to "Meus bots" only. */}
          {tab === "bots" && <ConversionOverview onPeriod={setPeriod} period={period} />}
          {tab === "flows" && (
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
            setRemarketingFlow(flowId);
            choose("remarketing");
          }}
          period={period}
        />
      )}
      {tab === "remarketing" && <RemarketingPanel flowId={remarketingFlow} onEditingChange={setEditing} onFlowChange={setRemarketingFlow} />}
      {tab === "shared" && <SharedFlowsPanel />}
      {tab === "sales" && <BotSalesPanel />}
    </div>
  );
}
