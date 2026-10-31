import { useState } from "react";
import { Copy, CreditCard, Eye, Gift, Plus, QrCode, ShieldCheck, ShoppingCart, Timer, Trash2, TrendingDown, TrendingUp, Truck } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { brl, emptyBump, emptyDelivery, emptyPreviews, type CustomOffer, type Delivery, type DownsellStep, type FlowDefinition, type Plan, type UpsellStep } from "../types";
import { BumpEditor, DeliveryEditor } from "./DeliveryEditor";
import { MediaGrid } from "./MediaGrid";
import { FontMenu, toFancy } from "./fancyFonts";
import { BASE_VARIABLES, RichTextEditor } from "./RichTextEditor";
import { SortableList } from "./SortableList";
import type { SectionProps } from "./sectionsTop";
import { Collapsible, DelayInput, DurationSelect, Field, MoneyInput, Panel, StylePicker, Switch } from "./ui";

const durationLabel = (days: number | null) =>
  days === null ? "Vitalício" : ({ 7: "Semanal", 15: "Quinzenal", 30: "Mensal", 90: "Trimestral", 180: "Semestral", 365: "Anual" } as Record<number, string>)[days] ?? `${days} dias`;

const delayLabel = (minutes: number) =>
  minutes === 0 ? "Imediato" : minutes % 1440 === 0 ? `${minutes / 1440} dia(s) depois` : minutes % 60 === 0 ? `${minutes / 60}h depois` : `${minutes} min depois`;

function useOpen() {
  const [open, setOpen] = useState<number | null>(0);
  return { open, toggle: (index: number) => setOpen((current) => (current === index ? null : index)), setOpen };
}

function StepActions({ onCopy, onRemove, canCopy }: { onCopy: () => void; onRemove: () => void; canCopy: boolean }) {
  return (
    <span className="flex gap-1">
      <button aria-label="Duplicar" className="btn-ghost !min-h-9 !px-2" disabled={!canCopy} onClick={onCopy} type="button">
        <Copy size={15} />
      </button>
      <button aria-label="Excluir" className="btn-ghost !min-h-9 !px-2 text-danger" onClick={onRemove} type="button">
        <Trash2 size={15} />
      </button>
    </span>
  );
}

// ---------------------------------------------------------------- Planos

function PlanEditor({ plan, onChange, hasDefaultBump }: { plan: Plan; onChange: (next: Plan) => void; hasDefaultBump: boolean }) {
  const set = (patch: Partial<Plan>) => onChange({ ...plan, ...patch });
  return (
    <>
      <Field label="Nome do plano">
        <input className="field" maxLength={60} value={plan.name} onChange={(event) => set({ name: event.target.value })} />
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <MoneyInput value={plan.price} onChange={(price) => set({ price })} />
        <DurationSelect value={plan.duration_days} onChange={(duration_days) => set({ duration_days })} />
      </div>
      <Field label="Texto do botão (opcional)" hint="Vazio = “Nome · Preço”. Use o Aa para letras personalizadas.">
        <div className="flex gap-1">
          <input className="field" maxLength={64} value={plan.button_text ?? ""} onChange={(event) => set({ button_text: event.target.value })} />
          <FontMenu
            compact
            onPick={(style) => set({ button_text: toFancy(plan.button_text || `${plan.name} · ${brl(plan.price || 0)}`, style).slice(0, 64) })}
          />
        </div>
      </Field>
      <StylePicker value={plan.button_style} onChange={(button_style) => set({ button_style })} />
      <div className="space-y-2 border-t border-line-soft pt-4">
        <p className="flex items-center gap-2 text-sm font-medium text-fg">
          <Truck size={15} className="text-success" /> Entrega deste plano
        </p>
        <select
          className="field"
          value={plan.delivery ? "own" : "default"}
          onChange={(event) => set({ delivery: event.target.value === "own" ? emptyDelivery("group") : null })}
        >
          <option value="default">Usar entrega padrão do fluxo</option>
          <option value="own">Entrega própria deste plano</option>
        </select>
        {plan.delivery && <DeliveryEditor value={plan.delivery} onChange={(delivery) => set({ delivery })} />}
      </div>
      <div className="space-y-2 border-t border-line-soft pt-4">
        <p className="flex items-center gap-2 text-sm font-medium text-fg">
          <ShoppingCart size={15} className="text-warning" /> Order bump
        </p>
        <select
          className="field"
          value={plan.bump_mode}
          onChange={(event) => {
            const bump_mode = event.target.value as Plan["bump_mode"];
            set({ bump_mode, order_bump: bump_mode === "custom" ? plan.order_bump ?? emptyBump() : plan.order_bump });
          }}
        >
          <option value="default">{hasDefaultBump ? "Usar o order bump padrão do fluxo" : "Padrão do fluxo (nenhum configurado)"}</option>
          <option value="custom">Order bump personalizado</option>
          <option value="off">Sem order bump neste plano</option>
        </select>
        {plan.bump_mode === "custom" && plan.order_bump && <BumpEditor value={plan.order_bump} onChange={(order_bump) => set({ order_bump })} />}
      </div>
    </>
  );
}

export function PlansSection({ draft, set }: SectionProps) {
  const { open, toggle, setOpen } = useOpen();
  const setPlan = (index: number, plan: Plan) => set({ plans: draft.plans.map((item, i) => (i === index ? plan : item)) });
  const newPlan = (base?: Plan): Plan => ({
    ...(base ?? { name: "Plano mensal", price: "29.90", duration_days: 30, button_text: null, button_style: "default", delivery: null, bump_mode: "default", order_bump: null }),
    id: `p${Date.now().toString(36)}`,
    name: base ? `${base.name} (cópia)`.slice(0, 60) : "Plano mensal",
  });
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px] xl:items-start">
    <Panel
      icon={<CreditCard size={18} />}
      title="Planos de pagamento"
      description="Cada plano vira um botão. O mínimo do Pix é R$ 1,00."
      aside={<span className="text-xs text-muted">{draft.plans.length}/10</span>}
    >
      <p className="text-xs text-muted">Segure e arraste o ⋮⋮ para mudar a ordem dos botões no bot.</p>
      <SortableList
        getKey={(plan) => plan.id}
        items={draft.plans}
        onDragStart={() => setOpen(null)}
        onReorder={(plans) => set({ plans })}
        render={(plan, index, handle) => (
          <Collapsible
            leading={handle}
            open={open === index}
            onToggle={() => toggle(index)}
            title={plan.name || "Sem nome"}
            subtitle={`${brl(plan.price || 0)} · ${durationLabel(plan.duration_days)} · ${plan.delivery ? "Entrega própria" : "Entrega padrão"}`}
            actions={
              <StepActions
                canCopy={draft.plans.length < 10}
                onCopy={() => set({ plans: [...draft.plans, newPlan(plan)] })}
                onRemove={() => set({ plans: draft.plans.filter((_, i) => i !== index) })}
              />
            }
          >
            <PlanEditor hasDefaultBump={Boolean(draft.order_bump)} plan={plan} onChange={(next) => setPlan(index, next)} />
          </Collapsible>
        )}
      />
      <Button
        disabled={draft.plans.length >= 10}
        onClick={() => {
          set({ plans: [...draft.plans, newPlan()] });
          setOpen(draft.plans.length);
        }}
        size="sm"
      >
        <Plus size={14} /> Adicionar plano
      </Button>
    </Panel>
    <DefaultDeliveryPanel draft={draft} set={set} />
    </div>
  );
}

// ---------------------------------------------------------------- Order bump

export function BumpSection({ draft, set }: SectionProps) {
  const using = draft.plans.filter((plan) => plan.bump_mode === "default").map((plan) => plan.name);
  return (
    <Panel
      icon={<ShoppingCart size={18} />}
      title="Order bump padrão"
      description="Pergunta “Adicionar X por +R$ Y?” antes de gerar o Pix. Se aceitar, sai um Pix único com o total."
      aside={<Switch checked={Boolean(draft.order_bump)} label="Order bump padrão" onChange={(on) => set({ order_bump: on ? draft.order_bump ?? emptyBump() : null })} />}
    >
      {draft.order_bump ? (
        <>
          <p className="text-xs text-muted">
            Vale para: {using.length ? using.join(", ") : "nenhum plano (todos têm bump personalizado ou desligado)"}.
          </p>
          <BumpEditor value={draft.order_bump} onChange={(order_bump) => set({ order_bump })} />
        </>
      ) : (
        <p className="text-sm text-muted">Desligado. Cada plano ainda pode ter um order bump personalizado na seção Planos.</p>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------- Upsell

function newUpsell(): UpsellStep {
  return {
    name: "Oferta especial",
    price: "19.90",
    duration_days: null,
    delay_minutes: 0,
    media_ids: [],
    spoiler: false,
    text: "Parabéns pela compra, {nome}! 🎉 Tenho uma oferta só pra você:",
    accept_label: "✅ Quero aproveitar",
    accept_style: "success",
    decline_label: "Não, obrigado",
    hide_decline: false,
    delivery: emptyDelivery("default"),
  };
}

/** "Entrega padrão do fluxo" or an own delivery (null = flow default). */
function OfferDelivery({ value, onChange, allowUpsell = false }: { value: Delivery | null; onChange: (next: Delivery | null) => void; allowUpsell?: boolean }) {
  return (
    <>
      <select className="field" value={value ? "own" : "default"} onChange={(event) => onChange(event.target.value === "own" ? emptyDelivery("default") : null)}>
        <option value="default">Usar entrega padrão do fluxo</option>
        <option value="own">Entrega própria desta oferta</option>
      </select>
      {value && <DeliveryEditor allowUpsell={allowUpsell} value={value} onChange={onChange} />}
    </>
  );
}

export function UpsellSection({ draft, set }: SectionProps) {
  const { open, toggle, setOpen } = useOpen();
  const setStep = (index: number, patch: Partial<UpsellStep>) =>
    set({ upsells: draft.upsells.map((item, i) => (i === index ? { ...item, ...patch } : item)) });
  return (
    <Panel
      icon={<TrendingUp size={18} />}
      title="Sequências de upsell"
      description="Ofertas enviadas depois que o lead paga. Recusou ou comprou, vai para a próxima."
      aside={<span className="text-xs text-muted">{draft.upsells.length}/20</span>}
    >
      <div className="space-y-2">
        {draft.upsells.map((step, index) => (
          <Collapsible
            key={index}
            open={open === index}
            onToggle={() => toggle(index)}
            title={`Sequência ${index + 1} · ${step.name}`}
            subtitle={`${brl(step.price || 0)} · na hora`}
            actions={
              <StepActions
                canCopy={draft.upsells.length < 20}
                onCopy={() => set({ upsells: [...draft.upsells, { ...step }] })}
                onRemove={() => set({ upsells: draft.upsells.filter((_, i) => i !== index) })}
              />
            }
          >
            <MediaGrid max={3} value={step.media_ids} onChange={(media_ids) => setStep(index, { media_ids })} />
            <RichTextEditor
              label="Mensagem"
              required
              rows={4}
              value={step.text}
              variables={[...BASE_VARIABLES, "{plano}", "{valor}"]}
              onChange={(text) => setStep(index, { text })}
            />
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Nome da oferta">
                <input className="field" maxLength={60} value={step.name} onChange={(event) => setStep(index, { name: event.target.value })} />
              </Field>
              <MoneyInput value={step.price} onChange={(price) => setStep(index, { price })} />
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Botão de aceitar">
                <input className="field" maxLength={64} value={step.accept_label} onChange={(event) => setStep(index, { accept_label: event.target.value })} />
              </Field>
              <Field label="Botão de recusar">
                <input
                  className="field disabled:opacity-40"
                  disabled={step.hide_decline}
                  maxLength={64}
                  value={step.decline_label}
                  onChange={(event) => setStep(index, { decline_label: event.target.value })}
                />
              </Field>
            </div>
            <StylePicker label="Cor do botão de aceitar" value={step.accept_style} onChange={(accept_style) => setStep(index, { accept_style })} />
            <label className="flex items-center justify-between gap-3 rounded-xl border border-line-soft p-3 text-sm text-fg-2">
              <span>
                Ocultar o botão de recusar
                <span className="block text-xs text-muted">Sem o “não”, a próxima oferta só é liberada quando o cliente pagar esta.</span>
              </span>
              <Switch checked={step.hide_decline} label="Ocultar o botão de recusar" onChange={(hide_decline) => setStep(index, { hide_decline })} />
            </label>
            <div className="space-y-2 border-t border-line-soft pt-4">
              <p className="flex items-center gap-2 text-sm font-medium text-fg">
                <Gift size={15} className="text-success" /> Entrega desta oferta
              </p>
              {(step.delivery?.type ?? draft.default_delivery?.type) === "group" && (
                <DurationSelect value={step.duration_days} onChange={(duration_days) => setStep(index, { duration_days })} />
              )}
              <OfferDelivery value={step.delivery} onChange={(delivery) => setStep(index, { delivery })} />
            </div>
          </Collapsible>
        ))}
      </div>
      <Button
        disabled={draft.upsells.length >= 20}
        onClick={() => {
          set({ upsells: [...draft.upsells, newUpsell()] });
          setOpen(draft.upsells.length);
        }}
        size="sm"
      >
        <Plus size={14} /> Adicionar sequência
      </Button>
    </Panel>
  );
}

// ---------------------------------------------------------------- Downsell

function newDownsell(index: number): DownsellStep {
  return {
    delay_minutes: index === 0 ? 30 : 60,
    media_ids: [],
    spoiler: false,
    text: "Ei {nome}, vi que você não finalizou… liberei <b>{desconto} de desconto</b> só pra você 👇",
    discount_type: "percent",
    discount_value: String(10 + index * 10),
    plan_ids: [],
    custom_offer: null,
    button_style: "success",
  };
}

const PERCENTS = Array.from({ length: 19 }, (_, i) => String((i + 1) * 5));

function newCustomOffer(): CustomOffer {
  return { name: "Oferta especial", price: "9.90", duration_days: 30, delivery: null };
}

const SEQUENCES = {
  pix: {
    label: "Pix gerado",
    hint: "Gerou o Pix e não pagou",
    first: "Enviar depois que o Pix foi gerado",
    icon: QrCode,
  },
  no_pix: {
    label: "Pix não gerado",
    hint: "Deu /start e não gerou o Pix",
    first: "Enviar depois do /start",
    icon: Timer,
  },
} as const;

type Sequence = keyof typeof SEQUENCES;

function DownsellList({ sequence, steps, plans, onChange }: { sequence: Sequence; steps: DownsellStep[]; plans: Plan[]; onChange: (next: DownsellStep[]) => void }) {
  const { open, toggle, setOpen } = useOpen();
  const setStep = (index: number, patch: Partial<DownsellStep>) => onChange(steps.map((item, i) => (i === index ? { ...item, ...patch } : item)));
  return (
    <>
      <div className="space-y-2">
        {steps.length === 0 && (
          <p className="rounded-xl border border-dashed border-line p-4 text-center text-sm text-muted">
            Nenhuma mensagem nesta sequência. Quem {sequence === "pix" ? "gerar o Pix e não pagar" : "não gerar o Pix"} não recebe downsell.
          </p>
        )}
        {steps.map((step, index) => (
          <Collapsible
            key={index}
            open={open === index}
            onToggle={() => toggle(index)}
            title={`Mensagem ${index + 1}`}
            subtitle={`${
              step.custom_offer
                ? `${step.custom_offer.name} · ${brl(step.custom_offer.price || 0)}`
                : `${step.discount_type === "percent" ? `${Number(step.discount_value)}%` : brl(step.discount_value || 0)} off`
            } · ${delayLabel(step.delay_minutes)}`}
            actions={
              <StepActions
                canCopy={steps.length < 20}
                onCopy={() => onChange([...steps, { ...step }])}
                onRemove={() => onChange(steps.filter((_, i) => i !== index))}
              />
            }
          >
            <MediaGrid max={3} value={step.media_ids} onChange={(media_ids) => setStep(index, { media_ids })} />
            <Field label={index === 0 ? SEQUENCES[sequence].first : "Enviar depois da mensagem anterior"}>
              <DelayInput allowZero={false} value={step.delay_minutes} onChange={(delay_minutes) => setStep(index, { delay_minutes })} />
            </Field>
            <label className="flex items-center justify-between gap-3 rounded-xl border border-line-soft p-3 text-sm text-fg-2">
              <span>
                Plano personalizado só desta oferta
                <span className="block text-xs text-muted">Em vez de desconto nos planos, oferece um plano com nome e preço próprios.</span>
              </span>
              <Switch
                checked={Boolean(step.custom_offer)}
                label="Plano personalizado"
                onChange={(on) => setStep(index, { custom_offer: on ? step.custom_offer ?? newCustomOffer() : null })}
              />
            </label>
            {step.custom_offer ? (
              <div className="grid gap-3 rounded-xl border border-line-soft p-3">
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="Nome do plano">
                    <input
                      className="field"
                      maxLength={60}
                      value={step.custom_offer.name}
                      onChange={(event) => setStep(index, { custom_offer: { ...step.custom_offer!, name: event.target.value } })}
                    />
                  </Field>
                  <MoneyInput value={step.custom_offer.price} onChange={(price) => setStep(index, { custom_offer: { ...step.custom_offer!, price } })} />
                </div>
                <DurationSelect value={step.custom_offer.duration_days} onChange={(duration_days) => setStep(index, { custom_offer: { ...step.custom_offer!, duration_days } })} />
                <OfferDelivery allowUpsell value={step.custom_offer.delivery} onChange={(delivery) => setStep(index, { custom_offer: { ...step.custom_offer!, delivery } })} />
              </div>
            ) : (
              <div className="grid grid-cols-[120px_1fr] gap-3">
                <Field label="Desconto">
                  <select
                    className="field"
                    value={step.discount_type}
                    onChange={(event) => {
                      const discount_type = event.target.value as "percent" | "fixed";
                      setStep(index, { discount_type, discount_value: discount_type === "percent" ? "10" : "5.00" });
                    }}
                  >
                    <option value="percent">%</option>
                    <option value="fixed">R$</option>
                  </select>
                </Field>
                {step.discount_type === "percent" ? (
                  <Field label="Porcentagem">
                    <select
                      className="field"
                      value={PERCENTS.includes(String(Number(step.discount_value))) ? String(Number(step.discount_value)) : step.discount_value}
                      onChange={(event) => setStep(index, { discount_value: event.target.value })}
                    >
                      {!PERCENTS.includes(String(Number(step.discount_value))) && <option value={step.discount_value}>{step.discount_value}%</option>}
                      {PERCENTS.map((value) => (
                        <option key={value} value={value}>
                          {value}% de desconto
                        </option>
                      ))}
                    </select>
                  </Field>
                ) : (
                  <Field label="Valor (R$)">
                    <input
                      className="field"
                      inputMode="decimal"
                      value={step.discount_value}
                      onChange={(event) => setStep(index, { discount_value: event.target.value.replace(/[^\d.,]/g, "") })}
                    />
                  </Field>
                )}
              </div>
            )}
            <RichTextEditor
              label="Mensagem"
              required
              rows={4}
              value={step.text}
              variables={[...BASE_VARIABLES, "{desconto}"]}
              onChange={(text) => setStep(index, { text })}
            />
            {!step.custom_offer && (
              <div className="grid gap-1.5 text-sm text-fg-2">
                <span>Planos oferecidos</span>
                <div className="flex flex-wrap gap-2">
                  {plans.map((plan) => {
                    const on = step.plan_ids.length === 0 || step.plan_ids.includes(plan.id);
                    return (
                      <button
                        aria-pressed={on}
                        className={`min-h-9 rounded-full border px-3 text-xs ${on ? "border-brand bg-brand-soft text-accent" : "border-line text-muted"}`}
                        key={plan.id}
                        onClick={() => {
                          const current = step.plan_ids.length ? step.plan_ids : plans.map((p) => p.id);
                          const next = on ? current.filter((id) => id !== plan.id) : [...current, plan.id];
                          setStep(index, { plan_ids: next.length === plans.length ? [] : next });
                        }}
                        type="button"
                      >
                        {plan.name}
                      </button>
                    );
                  })}
                  {plans.length === 0 && <span className="text-xs text-muted">Crie planos na seção Planos.</span>}
                </div>
              </div>
            )}
            <StylePicker value={step.button_style} onChange={(button_style) => setStep(index, { button_style })} />
          </Collapsible>
        ))}
      </div>
      <Button
        disabled={steps.length >= 20}
        onClick={() => {
          onChange([...steps, newDownsell(steps.length)]);
          setOpen(steps.length);
        }}
        size="sm"
      >
        <Plus size={14} /> Adicionar mensagem
      </Button>
    </>
  );
}

export function DownsellSection({ draft, set }: SectionProps) {
  const [sequence, setSequence] = useState<Sequence>("pix");
  const lists: Record<Sequence, DownsellStep[]> = { pix: draft.downsells, no_pix: draft.downsells_no_pix ?? [] };
  const update = (next: DownsellStep[]) => set(sequence === "pix" ? { downsells: next } : { downsells_no_pix: next });
  return (
    <Panel
      icon={<TrendingDown size={18} />}
      title="Downsell"
      description="Duas sequências separadas: uma para quem gerou o Pix e não pagou, outra para quem nem gerou. Param sozinhas assim que o lead paga."
      aside={<span className="text-xs text-muted">{lists[sequence].length}/20</span>}
    >
      <div className="grid grid-cols-2 gap-2" role="tablist" aria-label="Sequência de downsell">
        {(Object.keys(SEQUENCES) as Sequence[]).map((key) => {
          const item = SEQUENCES[key];
          const Icon = item.icon;
          const on = sequence === key;
          return (
            <button
              aria-selected={on}
              className={`flex items-center gap-3 rounded-xl border p-3 text-left transition ${on ? "border-brand bg-brand-soft" : "border-line bg-surface-inset hover:border-line-soft"}`}
              key={key}
              onClick={() => setSequence(key)}
              role="tab"
              type="button"
            >
              <span className={`grid size-9 shrink-0 place-items-center rounded-lg ${on ? "bg-brand text-white" : "bg-well text-muted"}`}>
                <Icon size={16} />
              </span>
              <span className="min-w-0">
                <span className={`block text-sm font-medium ${on ? "text-accent" : "text-fg"}`}>
                  {item.label} <span className="text-xs text-muted">· {lists[key].length}</span>
                </span>
                <span className="block truncate text-xs text-muted">{item.hint}</span>
              </span>
            </button>
          );
        })}
      </div>
      {sequence === "no_pix" && (
        <p className="text-xs leading-5 text-muted">Se o lead gerar o Pix no meio desta sequência, ela para e começa a sequência de Pix gerado.</p>
      )}
      <DownsellList key={sequence} onChange={update} plans={draft.plans} sequence={sequence} steps={lists[sequence]} />
    </Panel>
  );
}

// ---------------------------------------------------------------- Prévias

const PREVIEW_TIMES = [
  [10, "10 segundos"],
  [30, "30 segundos"],
  [60, "1 minuto"],
  [300, "5 minutos"],
  [900, "15 minutos"],
  [3600, "1 hora"],
  [21600, "6 horas"],
  [86400, "24 horas"],
] as const;

const timeUnits = [
  { value: 1, label: "segundos" },
  { value: 60, label: "minutos" },
  { value: 3600, label: "horas" },
];

export function PreviewsSection({ draft, set }: SectionProps) {
  const previews = draft.previews ?? emptyPreviews();
  const setPreviews = (patch: Partial<NonNullable<FlowDefinition["previews"]>>) => set({ previews: { ...previews, ...patch } });
  const seconds = previews.delete_after_seconds;
  const unit = seconds % 3600 === 0 ? 3600 : seconds % 60 === 0 ? 60 : 1;
  const clamp = (value: number) => Math.min(172800, Math.max(5, value));
  return (
    <Panel
      icon={<Eye size={18} />}
      title="Prévias"
      description="Um botão na boas-vindas que envia uma ou mais mídias de amostra. Elas se apagam sozinhas depois do tempo que você escolher."
      aside={<Switch checked={previews.enabled} label="Botão de prévias" onChange={(enabled) => setPreviews({ enabled })} />}
    >
      {previews.enabled ? (
        <div className="grid gap-4">
          <MediaGrid max={10} title="Mídias das prévias" value={previews.media_ids} onChange={(media_ids) => setPreviews({ media_ids })} />
          {previews.media_ids.length === 0 && <p className="text-xs text-warning">Adicione pelo menos uma mídia para o botão aparecer.</p>}
          <Field label="Apagar depois de" hint="O Telegram só deixa o bot apagar mensagens com até 48 horas.">
            <div className="grid gap-2">
              <div className="flex flex-wrap gap-2">
                {PREVIEW_TIMES.map(([value, label]) => (
                  <button
                    className={`min-h-9 rounded-full border px-3 text-xs ${seconds === value ? "border-brand bg-brand-soft text-accent" : "border-line text-muted"}`}
                    key={value}
                    onClick={() => setPreviews({ delete_after_seconds: value })}
                    type="button"
                  >
                    {label}
                  </button>
                ))}
              </div>
              <div className="flex items-center gap-2">
                <input
                  aria-label="Tempo até apagar"
                  className="field !w-24"
                  min={1}
                  type="number"
                  value={Math.max(1, Math.round(seconds / unit))}
                  onChange={(event) => setPreviews({ delete_after_seconds: clamp((Number(event.target.value) || 1) * unit) })}
                />
                <select
                  aria-label="Unidade"
                  className="field !w-auto"
                  value={unit}
                  onChange={(event) => setPreviews({ delete_after_seconds: clamp(Math.max(1, Math.round(seconds / unit)) * Number(event.target.value)) })}
                >
                  {timeUnits.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </Field>
          <RichTextEditor
            label="Legenda (opcional)"
            rows={2}
            value={previews.text ?? ""}
            variables={[...BASE_VARIABLES, "{tempo}"]}
            onChange={(text) => setPreviews({ text })}
          />
          <Field label="Texto do botão">
            <input className="field" maxLength={64} value={previews.label} onChange={(event) => setPreviews({ label: event.target.value })} />
          </Field>
          <StylePicker value={previews.style} onChange={(style) => setPreviews({ style })} />
          <label className="flex items-center justify-between gap-3 rounded-xl border border-line-soft p-3 text-sm text-fg-2">
            <span>
              Mídias com spoiler (borradas até tocar)
              <span className="block text-xs text-muted">As prévias também vão protegidas: o lead não consegue encaminhar nem salvar.</span>
            </span>
            <Switch checked={previews.spoiler} label="Spoiler nas prévias" onChange={(spoiler) => setPreviews({ spoiler })} />
          </label>
        </div>
      ) : (
        <p className="text-sm text-muted">Desligado. Ligue para mostrar o botão “{previews.label}” junto dos planos.</p>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------- Entrega, Pagamento, Configurações

function DefaultDeliveryPanel({ draft, set }: Pick<SectionProps, "draft" | "set">) {
  const using = draft.plans.filter((plan) => !plan.delivery).length;
  return (
    <Panel
      icon={<Truck size={18} />}
      title="Entrega padrão"
      description={`Usada quando o plano está em “Usar entrega padrão”${using ? ` (${using} plano(s) agora)` : ""}. Cada plano pode ter a própria.`}
      aside={<Switch checked={Boolean(draft.default_delivery)} label="Entrega padrão" onChange={(on) => set({ default_delivery: on ? draft.default_delivery ?? emptyDelivery("group") : null })} />}
    >
      {draft.default_delivery ? (
        <DeliveryEditor value={draft.default_delivery} onChange={(default_delivery) => set({ default_delivery })} />
      ) : (
        <p className="text-sm text-muted">Desligada: todos os planos precisam de entrega própria.</p>
      )}
    </Panel>
  );
}

export function PaymentSection({ draft, set }: SectionProps) {
  const payment = draft.payment;
  const setPayment = (patch: Partial<typeof payment>) => set({ payment: { ...payment, ...patch } });
  const vars = [...BASE_VARIABLES, "{plano}", "{valor}"];
  return (
    <Panel icon={<CreditCard size={18} />} title="Pagamento Pix" description="Textos do Pix e quanto tempo o código vale.">
      <Field label="Validade do Pix (minutos)">
        <input
          className="field !w-32"
          max={1440}
          min={5}
          type="number"
          value={payment.expiration_minutes}
          onChange={(event) => setPayment({ expiration_minutes: Math.min(1440, Math.max(5, Number(event.target.value) || 30)) })}
        />
      </Field>
      <RichTextEditor label="Mensagem do Pix" rows={3} value={payment.pix_text} variables={vars} onChange={(pix_text) => setPayment({ pix_text })} />
      <RichTextEditor label="Pagamento aprovado" rows={2} value={payment.approved_text} variables={vars} onChange={(approved_text) => setPayment({ approved_text })} />
      <RichTextEditor label="Pix expirado" rows={2} value={payment.expired_text} variables={vars} onChange={(expired_text) => setPayment({ expired_text })} />
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Botão copiar">
          <input className="field" maxLength={64} value={payment.copy_button} onChange={(event) => setPayment({ copy_button: event.target.value })} />
        </Field>
        <Field label="Botão verificar">
          <input className="field" maxLength={64} value={payment.check_button} onChange={(event) => setPayment({ check_button: event.target.value })} />
        </Field>
      </div>
      <Field label="Resposta ao “Já paguei” sem pagamento">
        <input className="field" maxLength={200} value={payment.pending_text} onChange={(event) => setPayment({ pending_text: event.target.value })} />
      </Field>
    </Panel>
  );
}

export function SettingsSection({ draft, set }: SectionProps) {
  const gate = draft.age_gate;
  return (
    <Panel
      icon={<ShieldCheck size={18} />}
      title="Verificação +18"
      description="Antes de tudo, o lead confirma a idade num botão."
      aside={<Switch checked={gate.enabled} label="Verificação +18" onChange={(enabled) => set({ age_gate: { ...gate, enabled } })} />}
    >
      {gate.enabled && (
        <div className="grid gap-3">
          <RichTextEditor label="Mensagem" rows={3} value={gate.text} onChange={(text) => set({ age_gate: { ...gate, text } })} />
          <Field label="Botão">
            <input className="field" maxLength={64} value={gate.button} onChange={(event) => set({ age_gate: { ...gate, button: event.target.value } })} />
          </Field>
        </div>
      )}
    </Panel>
  );
}
