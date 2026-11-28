import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FlaskConical, Pause, Trophy } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { confirmAction } from "@/lib/confirm";
import { ApiError, apiRequest } from "@/services/api";
import { moneyFormat } from "@/features/analytics/period";
import type { AbTest, AbVariantMetrics, Bot, Flow } from "./types";

const brl = (value: string) => moneyFormat.format(Number(value) || 0);
const pct = (value: number) => `${(value || 0).toLocaleString("pt-BR")}%`;

/** Which variant wins on conversion (ties and no-data = none). */
function leader(a: AbVariantMetrics, b: AbVariantMetrics): "a" | "b" | null {
  if (a.conversion === b.conversion) return null;
  return a.conversion > b.conversion ? "a" : "b";
}

function VariantColumn({
  label,
  name,
  weight,
  metrics,
  win,
}: {
  label: string;
  name: string;
  weight: number;
  metrics: AbVariantMetrics;
  win: boolean;
}) {
  const rows: [string, string][] = [
    ["Leads", metrics.leads.toLocaleString("pt-BR")],
    ["Pix gerados", metrics.pix.toLocaleString("pt-BR")],
    ["Vendas", metrics.sales.toLocaleString("pt-BR")],
    ["Conversão", pct(metrics.conversion)],
    ["Faturamento", brl(metrics.revenue)],
  ];
  return (
    <div className={`flex-1 rounded-xl border p-3 ${win ? "border-success/50 bg-success-soft" : "border-line bg-surface-inset"}`}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-muted">
          Versão {label} · {weight}%
        </span>
        {win && <Badge tone="success"><Trophy size={11} /> Melhor</Badge>}
      </div>
      <p className="mb-2 truncate text-sm font-semibold text-fg" title={name}>{name}</p>
      <dl className="grid gap-1 text-xs">
        {rows.map(([k, v]) => (
          <div className="flex justify-between gap-2" key={k}>
            <dt className="text-muted">{k}</dt>
            <dd className="font-semibold text-fg">{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function TestCard({ test, onChanged }: { test: AbTest; onChanged: () => void }) {
  const stop = useMutation({
    mutationFn: () => apiRequest(`/api/bots/ab-tests/${test.id}/stop`, { method: "POST" }),
    onSuccess: onChanged,
  });
  const remove = useMutation({
    mutationFn: () => apiRequest(`/api/bots/ab-tests/${test.id}`, { method: "DELETE" }),
    onSuccess: onChanged,
  });
  const win = test.results ? leader(test.results.a, test.results.b) : null;
  return (
    <article className="rounded-2xl border border-line bg-surface p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate font-semibold text-fg">{test.name}</p>
          <p className="text-xs text-muted">@{test.bot_username ?? "—"}</p>
        </div>
        <Badge tone={test.status === "active" ? "brand" : "neutral"}>
          {test.status === "active" ? "Ativo" : "Encerrado"}
        </Badge>
      </div>
      {test.results && (
        <div className="flex flex-col gap-2 sm:flex-row">
          <VariantColumn label="A" name={test.flow_a.name} weight={test.weight_a} metrics={test.results.a} win={win === "a"} />
          <VariantColumn label="B" name={test.flow_b.name} weight={100 - test.weight_a} metrics={test.results.b} win={win === "b"} />
        </div>
      )}
      <div className="mt-3 flex flex-wrap justify-end gap-1">
        {test.status === "active" && (
          <button className="btn-ghost !min-h-9 !px-2.5 text-xs" disabled={stop.isPending} onClick={() => stop.mutate()} type="button">
            <Pause size={14} /> Encerrar
          </button>
        )}
        <button
          className="btn-ghost !min-h-9 !px-2.5 text-xs text-danger"
          disabled={remove.isPending}
          onClick={async () => {
            if (await confirmAction(`Excluir o teste A/B “${test.name}”? Os funis e as vendas não são apagados, só o teste.`)) remove.mutate();
          }}
          type="button"
        >
          Excluir
        </button>
      </div>
      {(stop.error || remove.error) && (
        <p className="mt-2 text-xs text-danger">A ação não pôde ser concluída.</p>
      )}
    </article>
  );
}

/** Native A/B test: pick a bot and two funnel versions; the bot splits new leads between them
 *  by the chosen weight and the results show each version's conversion side by side. */
export function AbTestsModal({
  open,
  onClose,
  flows,
}: {
  open: boolean;
  onClose: () => void;
  flows: Flow[];
}) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("Teste A/B");
  const [botId, setBotId] = useState("");
  const [flowA, setFlowA] = useState("");
  const [flowB, setFlowB] = useState("");
  const [weightA, setWeightA] = useState(50);

  const ownFlows = useMemo(() => flows.filter((flow) => !flow.protected && !flow.from_template), [flows]);
  const bots = useQuery({
    queryKey: ["bots"],
    queryFn: () => apiRequest<{ bots: Bot[] }>("/api/bots"),
    enabled: open,
  });
  const tests = useQuery({
    queryKey: ["bots", "ab-tests"],
    queryFn: () => apiRequest<{ tests: AbTest[] }>("/api/bots/ab-tests"),
    enabled: open,
    refetchInterval: open ? 20_000 : false,
  });
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["bots", "ab-tests"] });
    void queryClient.invalidateQueries({ queryKey: ["bots"] });
  };
  const create = useMutation({
    mutationFn: () =>
      apiRequest<AbTest>("/api/bots/ab-tests", {
        method: "POST",
        body: { name: name.trim() || "Teste A/B", bot_id: botId, flow_a_id: flowA, flow_b_id: flowB, weight_a: weightA },
      }),
    onSuccess: () => {
      setName("Teste A/B");
      setFlowA("");
      setFlowB("");
      setWeightA(50);
      refresh();
    },
  });

  const chosenBot = bots.data?.bots.find((bot) => bot.id === botId);
  const valid = botId && flowA && flowB && flowA !== flowB;

  return (
    <Modal open={open} onClose={onClose} title="Teste A/B de funis" description="Rode duas versões do mesmo funil e veja qual converte melhor." wide busy={create.isPending}>
      <div className="grid gap-5">
        <form
          className="grid gap-3 rounded-2xl border border-line bg-surface-inset p-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (valid) create.mutate();
          }}
        >
          <label className="grid gap-1.5 text-sm text-fg-2">
            Nome do teste
            <input className="field" value={name} onChange={(event) => setName(event.target.value)} maxLength={120} />
          </label>
          <label className="grid gap-1.5 text-sm text-fg-2">
            Bot
            <select className="field" value={botId} onChange={(event) => setBotId(event.target.value)}>
              <option value="">Escolha o bot</option>
              {(bots.data?.bots ?? []).map((bot) => (
                <option key={bot.id} value={bot.id}>@{bot.username}</option>
              ))}
            </select>
          </label>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="grid gap-1.5 text-sm text-fg-2">
              Versão A
              <select className="field" value={flowA} onChange={(event) => setFlowA(event.target.value)}>
                <option value="">Escolha o funil</option>
                {ownFlows.map((flow) => (
                  <option key={flow.id} value={flow.id}>{flow.name}</option>
                ))}
              </select>
            </label>
            <label className="grid gap-1.5 text-sm text-fg-2">
              Versão B
              <select className="field" value={flowB} onChange={(event) => setFlowB(event.target.value)}>
                <option value="">Escolha o funil</option>
                {ownFlows.map((flow) => (
                  <option disabled={flow.id === flowA} key={flow.id} value={flow.id}>{flow.name}</option>
                ))}
              </select>
            </label>
          </div>
          <label className="grid gap-1.5 text-sm text-fg-2">
            Divisão dos leads — A {weightA}% / B {100 - weightA}%
            <input
              className="w-full accent-brand"
              max={99}
              min={1}
              onChange={(event) => setWeightA(Number(event.target.value))}
              type="range"
              value={weightA}
            />
          </label>
          {chosenBot?.folder_id && (
            <p className="text-xs text-warning">Este bot roda uma pasta de funis; o teste A/B vai substituir a pasta enquanto estiver ativo.</p>
          )}
          {create.error && (
            <p className="text-xs text-danger">{create.error instanceof ApiError ? create.error.message : "Não foi possível criar o teste."}</p>
          )}
          <div className="flex justify-end">
            <Button type="submit" variant="primary" disabled={!valid || create.isPending}>
              <FlaskConical size={16} /> Criar teste A/B
            </Button>
          </div>
        </form>

        <div className="grid gap-3">
          {tests.isLoading && <p className="text-sm text-muted">Carregando testes…</p>}
          {tests.data && tests.data.tests.length === 0 && (
            <p className="text-sm text-muted">Nenhum teste A/B ainda. Crie o primeiro acima.</p>
          )}
          {tests.data?.tests.map((test) => (
            <TestCard key={test.id} test={test} onChanged={refresh} />
          ))}
        </div>
      </div>
    </Modal>
  );
}
