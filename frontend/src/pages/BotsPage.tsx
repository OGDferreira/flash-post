import { useState } from "react";

import { BotSalesPanel } from "@/features/bots/BotSalesPanel";
import { BotsListPanel } from "@/features/bots/BotsListPanel";
import { FlowsPanel } from "@/features/bots/FlowsPanel";

const tabs = [
  { id: "bots", label: "Meus robôs" },
  { id: "flows", label: "Fluxos" },
  { id: "sales", label: "Vendas" },
] as const;

type Tab = (typeof tabs)[number]["id"];

export function BotsPage() {
  const [tab, setTab] = useState<Tab>("bots");
  return (
    <div className="mx-auto max-w-[1320px] space-y-4">
      <header>
        <p className="text-xs font-medium uppercase tracking-[0.16em] text-accent">Vendas</p>
        <h1 className="mt-2 text-2xl font-semibold text-fg sm:text-3xl">Robôs do Telegram</h1>
        <p className="mt-2 text-sm text-muted">
          Conecte seus robôs, monte o funil de cada um e acompanhe as vendas no Pix em tempo real.
        </p>
      </header>
      <div className="inline-flex gap-1 rounded-full bg-well p-1" role="tablist" aria-label="Seções dos robôs">
        {tabs.map((item) => (
          <button
            aria-selected={tab === item.id}
            className={`min-h-10 rounded-full px-4 text-sm font-medium ${tab === item.id ? "bg-brand text-white" : "text-muted"}`}
            key={item.id}
            onClick={() => setTab(item.id)}
            role="tab"
            type="button"
          >
            {item.label}
          </button>
        ))}
      </div>
      {tab === "bots" && <BotsListPanel />}
      {tab === "flows" && <FlowsPanel />}
      {tab === "sales" && <BotSalesPanel />}
    </div>
  );
}
