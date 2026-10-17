import { useState } from "react";

import { todayInput, type MetricsPeriod } from "@/features/analytics/period";
import { ConversionOverview } from "@/features/bots/ConversionOverview";

import { BotSalesPanel } from "@/features/bots/BotSalesPanel";
import { BotsListPanel } from "@/features/bots/BotsListPanel";
import { FlowsPanel } from "@/features/bots/FlowsPanel";
import { SharedFlowsPanel } from "@/features/partners/SharedTemplates";

const tabs = [
  { id: "bots", label: "Meus bots" },
  { id: "flows", label: "Meus funis" },
  { id: "shared", label: "Funis compartilhados" },
  { id: "sales", label: "Vendas" },
] as const;

type Tab = (typeof tabs)[number]["id"];

export function BotsPage() {
  const [tab, setTab] = useState<Tab>("bots");
  // The flow editor has its own header and section navigation; give it the whole screen.
  const [editing, setEditing] = useState(false);
  const [period, setPeriod] = useState<MetricsPeriod>({ period: "30d", start: todayInput(), end: todayInput() });
  return (
    <div className="mx-auto w-full max-w-[1500px] space-y-4">
      {!editing && (
        <>
          <header>
            <p className="text-xs font-medium uppercase tracking-[0.16em] text-accent">Vendas</p>
            <h1 className="mt-2 text-2xl font-semibold text-fg sm:text-3xl">FlashBot</h1>
            <p className="mt-2 text-sm text-muted">
              Seus robôs de venda no Telegram: conecte, monte o funil de cada um e acompanhe as vendas no Pix em tempo real.
            </p>
          </header>
          <ConversionOverview onPeriod={setPeriod} period={period} />
          <div className="inline-flex max-w-full gap-1 overflow-x-auto rounded-full bg-well p-1" role="tablist" aria-label="Seções dos robôs">
            {tabs.map((item) => (
              <button
                aria-selected={tab === item.id}
                className={`min-h-10 shrink-0 whitespace-nowrap rounded-full px-4 text-sm font-medium ${tab === item.id ? "bg-brand text-white" : "text-muted"}`}
                key={item.id}
                onClick={() => setTab(item.id)}
                role="tab"
                type="button"
              >
                {item.label}
              </button>
            ))}
          </div>
        </>
      )}
      {tab === "bots" && <BotsListPanel period={period} />}
      {tab === "flows" && <FlowsPanel onEditingChange={setEditing} period={period} />}
      {tab === "shared" && <SharedFlowsPanel />}
      {tab === "sales" && <BotSalesPanel />}
    </div>
  );
}
