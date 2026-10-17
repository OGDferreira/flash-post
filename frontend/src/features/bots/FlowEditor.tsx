import { useEffect, useMemo, useRef, useState, type ComponentType } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createPortal } from "react-dom";
import {
  ArrowLeft,
  Bot as BotIcon,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  CreditCard,
  Hand,
  Save,
  Settings2,
  ShoppingCart,
  Tags,
  TrendingDown,
  TrendingUp,
  Truck,
} from "lucide-react";

import { ErrorState, LoadingState } from "@/components/PageState";
import { confirmAction } from "@/lib/confirm";
import { ApiError, apiRequest } from "@/services/api";
import type { Delivery, Flow, FlowDefinition, OrderBump } from "./types";
import { BotsSection, WelcomeSection, type SectionProps } from "./editor/sectionsTop";
import {
  BumpSection,
  DeliverySection,
  DownsellSection,
  PaymentSection,
  PlansSection,
  SettingsSection,
  UpsellSection,
} from "./editor/sectionsOffers";

const sections: { id: string; label: string; icon: ComponentType<{ size?: number }>; component: ComponentType<SectionProps> }[] = [
  { id: "bots", label: "Bots", icon: BotIcon, component: BotsSection },
  { id: "welcome", label: "Boas-vindas", icon: Hand, component: WelcomeSection },
  { id: "plans", label: "Planos", icon: Tags, component: PlansSection },
  { id: "bump", label: "Order bump", icon: ShoppingCart, component: BumpSection },
  { id: "upsell", label: "Upsell", icon: TrendingUp, component: UpsellSection },
  { id: "downsell", label: "Downsell", icon: TrendingDown, component: DownsellSection },
  { id: "delivery", label: "Entrega padrão", icon: Truck, component: DeliverySection },
  { id: "payment", label: "Pagamento", icon: CreditCard, component: PaymentSection },
  { id: "settings", label: "Verificação +18", icon: Settings2, component: SettingsSection },
];

const blank = (value?: string | null) => (value && value.trim() ? value : null);
const money = (value: string | number) => Number(String(value).replace(",", ".")).toFixed(2);

function cleanDelivery<T extends Delivery | null | undefined>(delivery: T): T {
  if (!delivery) return delivery;
  return {
    ...delivery,
    group_chat_id: delivery.type === "group" ? delivery.group_chat_id ?? null : null,
    text: blank(delivery.text),
    media_ids: delivery.type === "group" ? [] : delivery.media_ids,
    link: delivery.link && delivery.link.label.trim() && delivery.link.url.trim() ? delivery.link : null,
  } as T;
}

function cleanBump(bump: OrderBump | null | undefined): OrderBump | null {
  return bump ? { ...bump, price: money(bump.price), delivery: cleanDelivery(bump.delivery) } : null;
}

/** Strips UI-only empties so the server validator sees exactly what the user set. */
function toPayload(definition: FlowDefinition): FlowDefinition {
  return {
    ...definition,
    welcome: definition.welcome.map((block) => ({
      ...block,
      text: block.type === "voice" || block.type === "video_note" ? null : blank(block.text),
      media_ids: block.type === "text" ? [] : block.media_ids,
    })),
    offer: {
      ...definition.offer,
      redirect_buttons: definition.offer.redirect_buttons.filter((item) => item.label.trim() && item.url.trim()),
    },
    plans: definition.plans.map((plan) => ({
      ...plan,
      price: money(plan.price),
      button_text: blank(plan.button_text),
      delivery: cleanDelivery(plan.delivery),
      order_bump: plan.bump_mode === "custom" ? cleanBump(plan.order_bump) : null,
    })),
    default_delivery: cleanDelivery(definition.default_delivery),
    order_bump: cleanBump(definition.order_bump),
    upsells: definition.upsells.map((step) => ({ ...step, price: money(step.price), delivery: cleanDelivery(step.delivery) })),
    downsells: definition.downsells.map((step) => ({
      ...step,
      discount_value: money(step.discount_value),
      custom_offer: step.custom_offer
        ? { ...step.custom_offer, price: money(step.custom_offer.price), delivery: cleanDelivery(step.custom_offer.delivery) }
        : null,
    })),
    support_username: blank(definition.support_username),
  };
}

export function FlowEditor({ flowId, onBack }: { flowId: string; onBack: () => void }) {
  const queryClient = useQueryClient();
  const flow = useQuery({ queryKey: ["bots", "flow", flowId], queryFn: () => apiRequest<Flow>(`/api/bots/flows/${flowId}`), retry: false });
  const [name, setName] = useState("");
  const [draft, setDraft] = useState<FlowDefinition | null>(null);
  const [savedJson, setSavedJson] = useState("");
  const [current, setCurrent] = useState(0);
  const [picker, setPicker] = useState(false);
  const [bottomPicker, setBottomPicker] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const top = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // The section bar takes the bottom of the screen; the global refresh button steps aside.
    document.body.dataset.flowEditor = "1";
    return () => {
      delete document.body.dataset.flowEditor;
    };
  }, []);
  useEffect(() => {
    if (flow.data && !draft) {
      setName(flow.data.name);
      setDraft(flow.data.definition);
      setSavedJson(JSON.stringify([flow.data.name, flow.data.definition]));
    }
  }, [flow.data, draft]);

  const dirty = useMemo(() => draft !== null && JSON.stringify([name, draft]) !== savedJson, [draft, name, savedJson]);

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const save = useMutation({
    mutationFn: () => apiRequest<Flow>(`/api/bots/flows/${flowId}`, { method: "PUT", body: { name, definition: toPayload(draft!) } }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["bots", "flow", flowId], updated);
      void queryClient.invalidateQueries({ queryKey: ["bots", "flows"] });
      setDraft(updated.definition);
      setName(updated.name);
      setSavedJson(JSON.stringify([updated.name, updated.definition]));
      setNotice("Fluxo salvo. Vale para os próximos leads.");
      window.setTimeout(() => setNotice(null), 2500);
    },
  });

  if (flow.isLoading || (flow.data && !draft)) return <LoadingState label="Abrindo fluxo" />;
  if (flow.error || !draft) {
    return (
      <ErrorState
        message={flow.error instanceof ApiError ? flow.error.message : "Não foi possível abrir o fluxo."}
        onRetry={() => void flow.refetch()}
      />
    );
  }

  const set = (patch: Partial<FlowDefinition>) => setDraft({ ...draft, ...patch });
  const section = sections[current];
  const Section = section.component;
  const go = (index: number) => {
    setCurrent(index);
    setPicker(false);
    setBottomPicker(false);
    top.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  const back = async () => {
    if (!dirty || (await confirmAction("Sair sem salvar? As alterações deste fluxo serão perdidas."))) onBack();
  };
  const SectionIcon = section.icon;

  return (
    <div className="space-y-4 pb-40 lg:pb-24" ref={top}>
      <div className="flex items-center gap-2">
        <button aria-label="Voltar para os fluxos" className="btn-secondary !min-h-11 !px-3" onClick={() => void back()} type="button">
          <ArrowLeft size={18} />
        </button>
        <div className="min-w-0 flex-1">
          <input
            aria-label="Nome do fluxo"
            className="w-full truncate bg-transparent text-lg font-semibold text-fg outline-none focus:underline"
            maxLength={120}
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <p className="text-[11px] uppercase tracking-[0.18em] text-muted">Editor de fluxo{dirty ? " · não salvo" : ""}</p>
        </div>
        <button className="btn-primary !min-h-11" disabled={save.isPending || !name.trim()} onClick={() => save.mutate()} type="button">
          <Save size={16} /> {save.isPending ? "Salvando…" : "Salvar"}
        </button>
      </div>

      {(save.error || notice) && (
        <p className={`rounded-xl border px-3 py-2 text-sm ${save.error ? "border-danger/30 bg-danger-soft text-danger" : "border-success/30 bg-success-soft text-success"}`} role="status">
          {save.error ? (save.error instanceof ApiError ? save.error.message : "Não foi possível salvar.") : notice}
        </p>
      )}

      <div className="relative">
        <button
          aria-expanded={picker}
          className="flex w-full items-center gap-3 rounded-2xl border border-line bg-surface p-3 text-left"
          onClick={() => setPicker(!picker)}
          type="button"
        >
          <span className="grid size-11 place-items-center rounded-xl bg-brand-soft text-accent">
            <SectionIcon size={20} />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-[11px] uppercase tracking-[0.18em] text-muted">Seção atual</span>
            <span className="block truncate font-medium text-fg">{section.label}</span>
          </span>
          <span className="text-sm text-muted">
            {current + 1} de {sections.length}
          </span>
          <ChevronDown className={`text-muted transition-transform ${picker ? "rotate-180" : ""}`} size={18} />
        </button>
        {picker && (
          <ul className="absolute inset-x-0 top-full z-30 mt-2 grid gap-0.5 rounded-2xl border border-line bg-[var(--nm-bg)] p-1.5 shadow-2xl" role="listbox">
            {sections.map((item, index) => {
              const Icon = item.icon;
              return (
                <li key={item.id}>
                  <button
                    aria-selected={index === current}
                    className={`flex min-h-11 w-full items-center gap-3 rounded-xl px-3 text-left text-sm ${index === current ? "nm-active font-medium" : "text-fg-2 hover:bg-well"}`}
                    onClick={() => go(index)}
                    role="option"
                    type="button"
                  >
                    <Icon size={16} />
                    <span className="flex-1">{item.label}</span>
                    <span className="text-xs text-muted">{index + 1}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <Section draft={draft} flowId={flowId} set={set} />

      {createPortal(
      <nav
        aria-label="Navegar entre seções"
        className="fixed bottom-[calc(env(safe-area-inset-bottom)+92px)] left-1/2 z-40 grid w-[calc(100vw-1.5rem)] max-w-xl -translate-x-1/2 grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-1.5 rounded-2xl border border-line bg-[var(--nm-bg)] p-1.5 shadow-2xl lg:bottom-6 lg:ml-[34px]"
      >
        <button
          aria-label={current > 0 ? `Voltar para ${sections[current - 1].label}` : "Primeira seção"}
          className="flex min-h-11 min-w-0 items-center gap-1 rounded-xl bg-well px-2 text-xs font-medium text-fg-2 disabled:opacity-30"
          disabled={current === 0}
          onClick={() => go(current - 1)}
          type="button"
        >
          <ChevronLeft className="shrink-0" size={18} />
          <span className="truncate">{current > 0 ? sections[current - 1].label : "Início"}</span>
        </button>
        <button
          aria-expanded={bottomPicker}
          aria-label="Ver todas as seções"
          className="flex min-h-11 max-w-[42vw] flex-col items-center justify-center rounded-xl px-2 hover:bg-well sm:max-w-none"
          onClick={() => setBottomPicker(!bottomPicker)}
          type="button"
        >
          <span className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-muted">
            {current + 1}/{sections.length} <ChevronUp className={`transition-transform ${bottomPicker ? "rotate-180" : ""}`} size={12} />
          </span>
          <span className="block max-w-full truncate text-sm font-semibold text-fg">{section.label}</span>
        </button>
        <button
          aria-label={current < sections.length - 1 ? `Avançar para ${sections[current + 1].label}` : "Última seção"}
          className="flex min-h-11 min-w-0 items-center justify-end gap-1 rounded-xl bg-brand px-2 text-xs font-semibold text-white disabled:bg-well disabled:text-fg-2 disabled:opacity-30"
          disabled={current === sections.length - 1}
          onClick={() => go(current + 1)}
          type="button"
        >
          <span className="truncate">{current < sections.length - 1 ? sections[current + 1].label : "Fim"}</span>
          <ChevronRight className="shrink-0" size={18} />
        </button>
      </nav>,
        document.body,
      )}
        {bottomPicker &&
          createPortal(
            <div className="fixed inset-0 z-[70]" role="presentation">
              <button aria-label="Fechar lista de seções" className="absolute inset-0 cursor-default bg-black/50" onClick={() => setBottomPicker(false)} type="button" />
          <ul
            className="absolute inset-x-3 bottom-[calc(env(safe-area-inset-bottom)+176px)] grid max-h-[calc(100dvh-280px)] gap-0.5 overflow-y-auto overscroll-contain rounded-2xl border border-line bg-[var(--nm-bg)] p-1.5 shadow-2xl sm:left-1/2 sm:right-auto sm:w-80 sm:-translate-x-1/2 lg:bottom-auto lg:top-1/2 lg:max-h-[80vh] lg:-translate-y-1/2"
            role="listbox"
          >
            {sections.map((item, index) => {
              const Icon = item.icon;
              return (
                <li key={item.id}>
                  <button
                    aria-selected={index === current}
                    className={`flex min-h-11 w-full items-center gap-3 rounded-xl px-3 text-left text-sm ${index === current ? "nm-active font-medium" : "text-fg-2 hover:bg-well"}`}
                    onClick={() => go(index)}
                    role="option"
                    type="button"
                  >
                    <Icon size={16} />
                    <span className="flex-1">{item.label}</span>
                    <span className="text-xs text-muted">{index + 1}</span>
                  </button>
                </li>
              );
            })}
          </ul>
            </div>,
            document.body,
          )}
    </div>
  );
}
