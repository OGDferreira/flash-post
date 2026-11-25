import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Check, FlaskConical, Image as ImageIcon, Layers } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { ApiError, apiRequest } from "@/services/api";
import {
  formatNumber,
  isPeriodReady,
  moneyFormat,
  PeriodFilter,
  periodParams,
  type MetricsPeriod,
} from "@/features/analytics/period";

/** One upsell step of a funnel, with how it sold in the chosen period. */
type Step = {
  flow_id: string;
  flow_name: string;
  index: number;
  name: string;
  price: string;
  pix: number;
  paid: number;
  revenue: number;
  conversion: number | null;
  has_media: boolean;
};

const money = (value: number) => moneyFormat.format(value || 0);
const brl = (value: string) => moneyFormat.format(Number(value) || 0);
const keyOf = (step: { flow_id: string; index: number }) => `${step.flow_id}:${step.index}`;

/** "Funil Frankenstein": pick the upsell steps that sell the most across every funnel and
 *  assemble a brand-new funnel from them. The new funnel opens in the editor to finish. */
export function FrankensteinModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (flowId: string) => void;
}) {
  const [period, setPeriod] = useState<MetricsPeriod>({ period: "30d", start: "", end: "" });
  const [picked, setPicked] = useState<string[]>([]);
  const [name, setName] = useState("Funil Frankenstein");

  const search = new URLSearchParams(periodParams(period));
  const query = useQuery({
    queryKey: ["bots", "frankenstein-steps", search.toString()],
    queryFn: () => apiRequest<{ period_label: string; steps: Step[] }>(`/api/bots/flows/frankenstein/steps?${search}`),
    enabled: open && isPeriodReady(period),
    placeholderData: (previous) => previous,
  });

  const byKey = useMemo(() => {
    const map = new Map<string, Step>();
    for (const step of query.data?.steps ?? []) map.set(keyOf(step), step);
    return map;
  }, [query.data]);

  const create = useMutation({
    mutationFn: () =>
      apiRequest<{ id: string }>("/api/bots/flows/frankenstein", {
        method: "POST",
        body: {
          name: name.trim() || "Funil Frankenstein",
          steps: picked.map((key) => {
            const step = byKey.get(key)!;
            return { flow_id: step.flow_id, index: step.index };
          }),
        },
      }),
    onSuccess: (flow) => {
      setPicked([]);
      onCreated(flow.id);
    },
  });

  const toggle = (key: string) =>
    setPicked((current) => (current.includes(key) ? current.filter((item) => item !== key) : [...current, key]));
  const move = (key: string, delta: number) =>
    setPicked((current) => {
      const index = current.indexOf(key);
      const next = index + delta;
      if (index < 0 || next < 0 || next >= current.length) return current;
      const copy = [...current];
      [copy[index], copy[next]] = [copy[next], copy[index]];
      return copy;
    });

  const steps = query.data?.steps ?? [];
  const ready = picked.length > 0 && name.trim().length > 0;

  return (
    <Modal
      busy={create.isPending}
      description="Escolha as etapas de upsell que mais vendem dos seus funis e monte um funil novo só com elas. Você termina de ajustar depois no editor."
      footer={
        <>
          <Button onClick={onClose}>Cancelar</Button>
          <Button disabled={!ready || create.isPending} onClick={() => create.mutate()} variant="primary">
            <FlaskConical size={16} /> {create.isPending ? "Montando…" : `Criar funil (${picked.length})`}
          </Button>
        </>
      }
      onClose={onClose}
      open={open}
      title="Montar funil Frankenstein"
      wide
    >
      <div className="space-y-4">
        <div className="grid gap-2.5 sm:grid-cols-2">
          <label className="grid gap-1.5 text-sm text-fg-2">
            Nome do novo funil
            <input className="field" maxLength={120} onChange={(event) => setName(event.target.value)} value={name} />
          </label>
          <div className="grid gap-1.5 text-sm text-fg-2">
            Ranking por período
            <PeriodFilter onChange={setPeriod} value={period} />
          </div>
        </div>

        {picked.length > 0 && (
          <div className="rounded-2xl border border-brand/40 bg-brand-soft p-3">
            <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[0.12em] text-accent">
              <Layers size={13} /> Etapas do novo funil · na ordem
            </p>
            <ol className="space-y-1.5">
              {picked.map((key, position) => {
                const step = byKey.get(key);
                if (!step) return null;
                return (
                  <li className="flex items-center gap-2 rounded-xl bg-surface p-2" key={key}>
                    <span className="grid size-6 shrink-0 place-items-center rounded-full bg-brand/15 text-xs font-bold text-accent">
                      {position + 1}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-sm text-fg">
                      {step.name} <span className="text-muted">· {step.flow_name}</span>
                    </span>
                    <span className="shrink-0 text-xs font-semibold text-fg-2 tabular-nums">{brl(step.price)}</span>
                    <button
                      aria-label="Subir"
                      className="btn-ghost !min-h-8 !px-1.5"
                      disabled={position === 0}
                      onClick={() => move(key, -1)}
                      type="button"
                    >
                      <ArrowUp size={14} />
                    </button>
                    <button
                      aria-label="Descer"
                      className="btn-ghost !min-h-8 !px-1.5"
                      disabled={position === picked.length - 1}
                      onClick={() => move(key, 1)}
                      type="button"
                    >
                      <ArrowDown size={14} />
                    </button>
                  </li>
                );
              })}
            </ol>
          </div>
        )}

        <div>
          <p className="mb-2 text-xs text-muted">
            {query.data ? `${formatNumber(steps.length)} etapas de upsell · ${query.data.period_label}` : "Carregando etapas…"}
          </p>
          {query.isError ? (
            <p className="text-sm text-danger">Não foi possível carregar as etapas.</p>
          ) : steps.length === 0 && query.data ? (
            <p className="rounded-xl border border-dashed border-line px-4 py-8 text-center text-sm text-muted">
              Nenhum funil seu tem etapas de upsell ainda. Adicione upsells a um funil para montar um Frankenstein.
            </p>
          ) : (
            <ul className="max-h-[46vh] space-y-2 overflow-y-auto pr-1">
              {steps.map((step, rank) => {
                const key = keyOf(step);
                const on = picked.includes(key);
                return (
                  <li key={key}>
                    <button
                      aria-pressed={on}
                      className={`flex w-full min-w-0 items-center gap-3 rounded-2xl border p-3 text-left transition-colors ${
                        on ? "border-brand bg-brand-soft" : "border-line-soft bg-surface-inset hover:border-line"
                      }`}
                      onClick={() => toggle(key)}
                      type="button"
                    >
                      <span
                        className={`grid size-6 shrink-0 place-items-center rounded-md border ${
                          on ? "border-brand bg-brand text-white" : "border-line text-transparent"
                        }`}
                      >
                        <Check size={14} />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center gap-1.5">
                          <span className="min-w-0 truncate text-sm font-medium text-fg">{step.name}</span>
                          {step.has_media && <ImageIcon className="shrink-0 text-muted" size={12} />}
                        </span>
                        <span className="truncate text-[11px] text-muted">
                          {step.flow_name} · etapa {step.index + 1} · {brl(step.price)}
                        </span>
                      </span>
                      <span className="shrink-0 text-right">
                        <span className="block text-sm font-bold text-success tabular-nums">{money(step.revenue)}</span>
                        <span className="block text-[11px] text-muted tabular-nums">
                          {formatNumber(step.paid)} {step.paid === 1 ? "venda" : "vendas"}
                          {step.conversion != null && ` · ${step.conversion.toLocaleString("pt-BR")}%`}
                        </span>
                      </span>
                      {rank < 3 && step.revenue > 0 && (
                        <span className="shrink-0 rounded-full bg-success/12 px-2 py-0.5 text-[10px] font-semibold text-success">
                          Top {rank + 1}
                        </span>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {create.error && (
          <p className="text-xs text-danger">
            {create.error instanceof ApiError ? create.error.message : "Não foi possível montar o funil."}
          </p>
        )}
      </div>
    </Modal>
  );
}
