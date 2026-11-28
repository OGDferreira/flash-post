import { useState } from "react";
import { Copy, CreditCard, Eye, Gift, MessageSquare, Plus, QrCode, RefreshCw, ShieldCheck, ShoppingCart, Timer, Trash2, TrendingDown, TrendingUp, Truck } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { brl, emptyBump, emptyDelivery, emptyFollowUp, emptyGroupPreview, emptyMimo, emptyPaymentRecovery, emptyPreviews, emptySmartReplies, type CustomOffer, type Delivery, type DownsellStep, type FlowDefinition, type FollowUpStep, type PaymentRecovery, type Plan, type SmartReplyRule, type SmartThen, type UpsellStep } from "../types";
import { BumpEditor, DeliveryEditor, useBotGroups } from "./DeliveryEditor";
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

// Optional per-offer "payment approved" message. Empty/null = the funnel's default
// (Pagamentos → "Mensagem de pagamento aprovado") is used for this offer.
function ApprovedMessageField({
  value,
  mediaIds,
  spoiler,
  onChange,
  onMediaChange,
  onSpoilerChange,
}: {
  value: string | null | undefined;
  mediaIds?: string[];
  spoiler?: boolean;
  onChange: (next: string | null) => void;
  onMediaChange: (next: string[]) => void;
  onSpoilerChange: (next: boolean) => void;
}) {
  const custom = value != null;
  return (
    <div className="space-y-2 rounded-xl border border-line-soft p-3">
      <Switch
        checked={custom}
        label="Mensagem de pagamento aprovado própria"
        onChange={(on) => onChange(on ? value ?? "" : null)}
      />
      {custom ? (
        <>
          <RichTextEditor
            label="Mensagem desta oferta"
            rows={3}
            value={value ?? ""}
            variables={BASE_VARIABLES}
            onChange={(text) => onChange(text)}
          />
          <MediaGrid
            kinds={["photo", "video"]}
            max={3}
            title="Imagem junto da mensagem (opcional)"
            value={mediaIds ?? []}
            onChange={onMediaChange}
          />
          {(mediaIds?.length ?? 0) > 0 && (
            <label className="flex items-center justify-between gap-3 text-sm text-fg-2">
              <span>Borrar a mídia (spoiler)</span>
              <Switch checked={!!spoiler} label="Borrar a mídia" onChange={onSpoilerChange} />
            </label>
          )}
          <p className="text-[11px] text-muted">
            Substitui a mensagem padrão do funil só para esta oferta.
            {(mediaIds?.length ?? 0) > 0 && " A imagem vai junto do texto, na mesma mensagem."}
          </p>
        </>
      ) : (
        <p className="text-[11px] text-muted">Usa a mensagem padrão do funil (aba Pagamentos).</p>
      )}
    </div>
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
      <Field label="Texto do botão (opcional)" hint="Vazio = &ldquo;Nome · Preço&rdquo;. Use o Aa para letras personalizadas.">
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
        {plan.bump_mode === "custom" && plan.order_bump && <BumpEditor allowDefault value={plan.order_bump} onChange={(order_bump) => set({ order_bump })} />}
      </div>
      <div className="border-t border-line-soft pt-4">
        <ApprovedMessageField value={plan.approved_text} mediaIds={plan.approved_media_ids} spoiler={plan.approved_spoiler} onChange={(approved_text) => set({ approved_text })} onMediaChange={(approved_media_ids) => set({ approved_media_ids })} onSpoilerChange={(approved_spoiler) => set({ approved_spoiler })} />
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
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_380px] xl:items-start [&>*]:min-w-0">
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
      description="Pergunta &ldquo;Adicionar X por +R$ Y?&rdquo; antes de gerar o Pix. Se aceitar, sai um Pix único com o total."
      aside={<Switch checked={Boolean(draft.order_bump)} label="Order bump padrão" onChange={(on) => set({ order_bump: on ? draft.order_bump ?? emptyBump() : null })} />}
    >
      {draft.order_bump ? (
        <>
          <p className="text-xs text-muted">
            Vale para: {using.length ? using.join(", ") : "nenhum plano (todos têm bump personalizado ou desligado)"}.
          </p>
          <BumpEditor allowDefault value={draft.order_bump} onChange={(order_bump) => set({ order_bump })} />
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
  const [bulkMedia, setBulkMedia] = useState<string[]>([]);
  const setStep = (index: number, patch: Partial<UpsellStep>) =>
    set({ upsells: draft.upsells.map((item, i) => (i === index ? { ...item, ...patch } : item)) });
  return (
    <Panel
      icon={<TrendingUp size={18} />}
      title="Sequências de upsell"
      description="Ofertas enviadas depois que o lead paga. Recusou ou comprou, vai para a próxima."
      aside={<span className="text-xs text-muted">{draft.upsells.length}/20</span>}
    >
      {draft.upsells.length > 1 && (
        <div className="mb-3 space-y-2 rounded-xl border border-line-soft p-3">
          <p className="text-sm font-medium text-fg">Alterar a mídia de todos os upsells de uma vez</p>
          <p className="text-xs text-muted">
            Escolha a mídia e aplique às {draft.upsells.length} sequências. Troca só o arquivo; o resto de cada upsell continua igual.
          </p>
          <MediaGrid max={3} title="Mídia para todos os upsells" value={bulkMedia} onChange={setBulkMedia} />
          <Button
            disabled={!bulkMedia.length}
            onClick={() => set({ upsells: draft.upsells.map((step) => ({ ...step, media_ids: [...bulkMedia] })) })}
            size="sm"
          >
            Aplicar a todos os upsells
          </Button>
        </div>
      )}
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
                <span className="block text-xs text-muted">Sem o "não", a próxima oferta só é liberada quando o cliente pagar esta.</span>
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
              <ApprovedMessageField value={step.approved_text} mediaIds={step.approved_media_ids} spoiler={step.approved_spoiler} onChange={(approved_text) => setStep(index, { approved_text })} onMediaChange={(approved_media_ids) => setStep(index, { approved_media_ids })} onSpoilerChange={(approved_spoiler) => setStep(index, { approved_spoiler })} />
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
                <ApprovedMessageField value={step.custom_offer.approved_text} mediaIds={step.custom_offer.approved_media_ids} spoiler={step.custom_offer.approved_spoiler} onChange={(approved_text) => setStep(index, { custom_offer: { ...step.custom_offer!, approved_text } })} onMediaChange={(approved_media_ids) => setStep(index, { custom_offer: { ...step.custom_offer!, approved_media_ids } })} onSpoilerChange={(approved_spoiler) => setStep(index, { custom_offer: { ...step.custom_offer!, approved_spoiler } })} />
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

const GROUP_PREVIEW_TIMES = [
  [30, "30 segundos"],
  [60, "1 minuto"],
  [300, "5 minutos"],
  [600, "10 minutos"],
  [1800, "30 minutos"],
  [3600, "1 hora"],
  [86400, "24 horas"],
] as const;

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
        <p className="text-sm text-muted">Desligado. Ligue para mostrar o botão "{previews.label}" junto dos planos.</p>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------- Prévia de grupo

export function GroupPreviewSection({ draft, set }: SectionProps) {
  const gp = draft.group_preview ?? emptyGroupPreview();
  const setGp = (patch: Partial<NonNullable<FlowDefinition["group_preview"]>>) => set({ group_preview: { ...gp, ...patch } });
  const groups = useBotGroups().data?.groups ?? [];
  const seconds = gp.access_seconds;
  const unit = seconds % 3600 === 0 ? 3600 : seconds % 60 === 0 ? 60 : 1;
  const clamp = (value: number) => Math.min(86400, Math.max(10, value));
  return (
    <Panel
      icon={<Gift size={18} />}
      title="Prévia de grupo"
      description="Um botão na boas-vindas que dá acesso temporário ao seu grupo/canal. O lead entra por um convite de uso único e o bot o remove sozinho quando o tempo acaba."
      aside={<Switch checked={gp.enabled} label="Prévia de grupo" onChange={(enabled) => setGp({ enabled })} />}
    >
      {gp.enabled ? (
        <div className="grid gap-4">
          <Field
            label="Grupo ou canal"
            hint="Aparecem os grupos onde um bot seu é administrador com permissão de convidar e de remover membros."
          >
            <select
              className="field"
              value={gp.group_chat_id ?? ""}
              onChange={(event) => setGp({ group_chat_id: event.target.value ? Number(event.target.value) : null })}
            >
              <option value="">Escolha…</option>
              {groups.map((group) => (
                <option disabled={!group.can_invite} key={group.chat_id} value={group.chat_id}>
                  {group.title} (@{group.bot}){group.can_invite ? "" : " — sem permissão de convidar"}
                </option>
              ))}
            </select>
          </Field>
          {!gp.group_chat_id && <p className="text-xs text-warning">Escolha o grupo para o botão aparecer.</p>}
          <Field label="Tempo de acesso" hint="Depois desse tempo o bot remove o lead do grupo automaticamente.">
            <div className="grid gap-2">
              <div className="flex flex-wrap gap-2">
                {GROUP_PREVIEW_TIMES.map(([value, label]) => (
                  <button
                    className={`min-h-9 rounded-full border px-3 text-xs ${seconds === value ? "border-brand bg-brand-soft text-accent" : "border-line text-muted"}`}
                    key={value}
                    onClick={() => setGp({ access_seconds: value })}
                    type="button"
                  >
                    {label}
                  </button>
                ))}
              </div>
              <div className="flex items-center gap-2">
                <input
                  aria-label="Tempo de acesso"
                  className="field !w-24"
                  min={1}
                  type="number"
                  value={Math.max(1, Math.round(seconds / unit))}
                  onChange={(event) => setGp({ access_seconds: clamp((Number(event.target.value) || 1) * unit) })}
                />
                <select
                  aria-label="Unidade"
                  className="field !w-auto"
                  value={unit}
                  onChange={(event) => setGp({ access_seconds: clamp(Math.max(1, Math.round(seconds / unit)) * Number(event.target.value)) })}
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
            label="Mensagem ao liberar"
            rows={2}
            value={gp.grant_text ?? ""}
            variables={[...BASE_VARIABLES, "{tempo}"]}
            onChange={(grant_text) => setGp({ grant_text })}
          />
          <Field label="Texto do botão de entrada">
            <input className="field" maxLength={64} value={gp.join_label} onChange={(event) => setGp({ join_label: event.target.value })} />
          </Field>
          <RichTextEditor
            label="Mensagem quando o acesso expira"
            rows={2}
            value={gp.expired_text}
            variables={BASE_VARIABLES}
            onChange={(expired_text) => setGp({ expired_text })}
          />
          <Field label="Texto do botão">
            <input className="field" maxLength={64} value={gp.label} onChange={(event) => setGp({ label: event.target.value })} />
          </Field>
          <StylePicker value={gp.style} onChange={(style) => setGp({ style })} />
        </div>
      ) : (
        <p className="text-sm text-muted">Desligado. Ligue para mostrar o botão "{gp.label}" junto dos planos.</p>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------- Mimo (gorjeta)

export function MimoSection({ draft, set }: SectionProps) {
  const mimo = draft.mimo ?? emptyMimo();
  const setMimo = (patch: Partial<NonNullable<FlowDefinition["mimo"]>>) => set({ mimo: { ...mimo, ...patch } });
  return (
    <Panel
      icon={<Gift size={18} />}
      title="Mimo"
      description="Um botão na boas-vindas; o lead digita o valor que quiser e recebe um Pix para pagar. Não entrega conteúdo nem dispara upsell — é só um carinho em dinheiro."
      aside={<Switch checked={mimo.enabled} label="Mimo" onChange={(enabled) => setMimo({ enabled })} />}
    >
      {mimo.enabled ? (
        <div className="grid gap-4">
          <RichTextEditor
            label="Pergunta do valor"
            rows={2}
            value={mimo.prompt_text}
            variables={BASE_VARIABLES}
            onChange={(prompt_text) => setMimo({ prompt_text })}
          />
          <div className="grid grid-cols-2 gap-3">
            <MoneyInput label="Valor mínimo (R$)" value={mimo.min_amount} onChange={(min_amount) => setMimo({ min_amount })} />
            <MoneyInput label="Valor máximo (R$)" value={mimo.max_amount} onChange={(max_amount) => setMimo({ max_amount })} />
          </div>
          <RichTextEditor
            label="Mensagem de valor inválido"
            rows={2}
            value={mimo.invalid_text}
            variables={[...BASE_VARIABLES, "{min}", "{max}"]}
            onChange={(invalid_text) => setMimo({ invalid_text })}
          />
          <RichTextEditor
            label="Agradecimento após o pagamento"
            rows={2}
            value={mimo.thanks_text}
            variables={[...BASE_VARIABLES, "{valor}"]}
            onChange={(thanks_text) => setMimo({ thanks_text })}
          />
          <Field label="Texto do botão">
            <input className="field" maxLength={64} value={mimo.label} onChange={(event) => setMimo({ label: event.target.value })} />
          </Field>
          <StylePicker value={mimo.style} onChange={(style) => setMimo({ style })} />
        </div>
      ) : (
        <p className="text-sm text-muted">Desligado. Ligue para mostrar o botão "{mimo.label}" junto dos planos.</p>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------- Respostas no DM

const THEN_OPTIONS: { value: SmartThen; label: string }[] = [
  { value: "none", label: "Só responder" },
  { value: "plans", label: "Responder e reenviar os planos" },
  { value: "offer", label: "Responder e reenviar a oferta" },
];

function ThenPicker({ value, onChange }: { value: SmartThen; onChange: (value: SmartThen) => void }) {
  return (
    <Field label="Depois de responder">
      <select className="field" value={value} onChange={(event) => onChange(event.target.value as SmartThen)}>
        {THEN_OPTIONS.map((item) => (
          <option key={item.value} value={item.value}>
            {item.label}
          </option>
        ))}
      </select>
    </Field>
  );
}

export function SmartRepliesSection({ draft, set }: SectionProps) {
  const smart = draft.smart_replies ?? emptySmartReplies();
  const setSmart = (patch: Partial<NonNullable<FlowDefinition["smart_replies"]>>) => set({ smart_replies: { ...smart, ...patch } });
  const setRule = (index: number, patch: Partial<SmartReplyRule>) =>
    setSmart({ rules: smart.rules.map((rule, i) => (i === index ? { ...rule, ...patch } : rule)) });
  const addRule = () => setSmart({ rules: [...smart.rules, { keywords: [], reply: "", then: "none" }] });
  const removeRule = (index: number) => setSmart({ rules: smart.rules.filter((_, i) => i !== index) });

  return (
    <Panel
      icon={<MessageSquare size={18} />}
      title="Respostas no DM"
      description="Quando o lead escreve algo fora do script (uma dúvida, uma objeção) em vez de tocar num botão, o bot reconhece por palavra-chave e responde — e pode reenviar os planos para manter a conversa andando. Desligado, o bot fica em silêncio como antes."
      aside={<Switch checked={smart.enabled} label="Respostas no DM" onChange={(enabled) => setSmart({ enabled })} />}
    >
      {smart.enabled ? (
        <div className="grid gap-4">
          <div className="grid gap-3">
            {smart.rules.map((rule, index) => (
              <div className="grid gap-3 rounded-xl border border-line-soft p-3" key={index}>
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-fg">Regra {index + 1}</span>
                  <button aria-label="Remover regra" className="text-muted hover:text-danger" onClick={() => removeRule(index)} type="button">
                    <Trash2 size={16} />
                  </button>
                </div>
                <Field label="Palavras-chave" hint="Separe por vírgula. Basta uma aparecer na mensagem (ignora maiúsculas e acentos).">
                  <input
                    className="field"
                    placeholder="preço, quanto custa, valor"
                    value={rule.keywords.join(", ")}
                    onChange={(event) =>
                      setRule(index, {
                        keywords: event.target.value
                          .split(",")
                          .map((word) => word.trim())
                          .filter(Boolean)
                          .slice(0, 20),
                      })
                    }
                  />
                </Field>
                <RichTextEditor
                  label="Resposta"
                  required
                  rows={2}
                  value={rule.reply}
                  variables={BASE_VARIABLES}
                  onChange={(reply) => setRule(index, { reply })}
                />
                <ThenPicker value={rule.then} onChange={(then) => setRule(index, { then })} />
              </div>
            ))}
            <Button disabled={smart.rules.length >= 30} size="sm" onClick={addRule}>
              <Plus size={16} /> Adicionar palavra-chave
            </Button>
          </div>
          <label className="flex items-center justify-between gap-3 rounded-xl border border-line-soft p-3 text-sm text-fg-2">
            <span>
              Resposta padrão (fallback)
              <span className="block text-xs text-muted">Quando a mensagem não bate com nenhuma palavra-chave acima.</span>
            </span>
            <Switch checked={smart.fallback_enabled} label="Fallback" onChange={(fallback_enabled) => setSmart({ fallback_enabled })} />
          </label>
          {smart.fallback_enabled && (
            <div className="grid gap-3">
              <RichTextEditor
                label="Mensagem de fallback"
                required
                rows={2}
                value={smart.fallback_text}
                variables={BASE_VARIABLES}
                onChange={(fallback_text) => setSmart({ fallback_text })}
              />
              <ThenPicker value={smart.fallback_then} onChange={(fallback_then) => setSmart({ fallback_then })} />
            </div>
          )}
          <p className="text-xs text-muted">
            Dica: use variações com <code>{"{a|b|c}"}</code> na resposta para o bot não soar robótico (ele sorteia uma a cada envio).
          </p>
        </div>
      ) : (
        <p className="text-sm text-muted">Desligado. Ligue para o bot responder quando o lead digitar algo em vez de tocar nos botões.</p>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------- Retomada de conversa

export function FollowUpSection({ draft, set }: SectionProps) {
  const fu = draft.follow_up ?? emptyFollowUp();
  const setFu = (patch: Partial<NonNullable<FlowDefinition["follow_up"]>>) => set({ follow_up: { ...fu, ...patch } });
  const setStep = (index: number, patch: Partial<FollowUpStep>) =>
    setFu({ steps: fu.steps.map((step, i) => (i === index ? { ...step, ...patch } : step)) });
  const addStep = () => setFu({ steps: [...fu.steps, { delay_minutes: fu.steps.length ? 1440 : 60, text: "", media_ids: [], spoiler: false }] });
  const removeStep = (index: number) => setFu({ steps: fu.steps.filter((_, i) => i !== index) });

  return (
    <Panel
      icon={<RefreshCw size={18} />}
      title="Retomada de conversa"
      description="Se o lead some no meio do funil (sem responder), o bot manda um follow-up automático para trazer de volta. Cada tentativa tem seu próprio tempo de espera e mensagem. O tempo reinicia a cada ação do lead e a sequência para quando ele paga ou gera o Pix."
      aside={<Switch checked={fu.enabled} label="Retomada" onChange={(enabled) => setFu({ enabled })} />}
    >
      {fu.enabled ? (
        <div className="grid gap-4">
          {fu.steps.length === 0 && <p className="text-xs text-warning">Adicione pelo menos uma tentativa de retomada.</p>}
          <div className="grid gap-3">
            {fu.steps.map((step, index) => (
              <div className="grid gap-3 rounded-xl border border-line-soft p-3" key={index}>
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-fg">Tentativa {index + 1}</span>
                  <button aria-label="Remover tentativa" className="text-muted hover:text-danger" onClick={() => removeStep(index)} type="button">
                    <Trash2 size={16} />
                  </button>
                </div>
                <Field label="Esperar" hint={index === 0 ? "Tempo sem resposta do lead antes deste follow-up." : "Tempo após a tentativa anterior."}>
                  <DelayInput value={step.delay_minutes} allowZero={false} onChange={(delay_minutes) => setStep(index, { delay_minutes })} />
                </Field>
                <RichTextEditor
                  label="Mensagem"
                  rows={3}
                  value={step.text ?? ""}
                  variables={BASE_VARIABLES}
                  onChange={(text) => setStep(index, { text })}
                />
                <MediaGrid max={3} title="Mídia (opcional)" value={step.media_ids} onChange={(media_ids) => setStep(index, { media_ids })} />
                {step.media_ids.length > 0 && (
                  <label className="flex items-center justify-between gap-3 text-sm text-fg-2">
                    <span>Borrar mídia (spoiler)</span>
                    <Switch checked={step.spoiler} label="Spoiler" onChange={(spoiler) => setStep(index, { spoiler })} />
                  </label>
                )}
              </div>
            ))}
            <Button disabled={fu.steps.length >= 10} size="sm" onClick={addStep}>
              <Plus size={16} /> Adicionar tentativa
            </Button>
          </div>
        </div>
      ) : (
        <p className="text-sm text-muted">Desligado. Ligue para o bot reengajar leads que pararam de responder no meio do funil.</p>
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
      description={`Usada quando o plano está em "Usar entrega padrão"${using ? ` (${using} plano(s) agora)` : ""}. Cada plano pode ter a própria.`}
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

const STEPS_TEXT =
  "✅ <b>Como realizar o pagamento:</b>\n\n1. Abra o aplicativo do seu banco.\n2. Selecione a opção \"Pagar\" ou \"PIX\".\n" +
  "3. Escolha \"PIX Copia e Cola\".\n4. Cole a chave que está abaixo e finalize o pagamento com segurança.";

export function PaymentSection({ draft, set }: SectionProps) {
  const payment = draft.payment;
  const setPayment = (patch: Partial<typeof payment>) => set({ payment: { ...payment, ...patch } });
  const vars = [...BASE_VARIABLES, "{plano}", "{valor}"];
  // The two modes can be on at once; legacy funnels only carry ``layout``.
  const qrOn = payment.qr_enabled ?? ((payment.layout ?? "qr") === "qr");
  const stepsOn = payment.steps_enabled ?? ((payment.layout ?? "qr") === "steps");
  const setModes = (qr: boolean, steps: boolean) => {
    if (!qr && !steps) return; // keep at least one way to pay
    setPayment({ qr_enabled: qr, steps_enabled: steps, layout: qr ? "qr" : "steps" });
  };
  // "Ambos" = QR Code + passo a passo + Pix copia e cola juntos.
  const pixMode: "qr" | "steps" | "both" = qrOn && stepsOn ? "both" : stepsOn ? "steps" : "qr";
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

      <div className="space-y-2 rounded-xl border border-line-soft p-3">
        <Switch
          checked={!!payment.intro_enabled}
          label="Mensagem antes do pagamento"
          onChange={(intro_enabled) => setPayment({ intro_enabled })}
        />
        <p className="text-xs text-muted">Enviada logo antes do Pix: uma mídia e/ou um texto para preparar o lead.</p>
        {payment.intro_enabled && (
          <div className="space-y-2">
            <MediaGrid
              kinds={["photo", "video"]}
              max={3}
              title="Mídia da mensagem"
              value={payment.intro_media_ids ?? []}
              onChange={(intro_media_ids) => setPayment({ intro_media_ids })}
            />
            <label className="flex items-center justify-between gap-3 text-sm text-fg-2">
              <span>Borrar a mídia (spoiler)</span>
              <Switch checked={!!payment.intro_spoiler} label="Borrar a mídia" onChange={(intro_spoiler) => setPayment({ intro_spoiler })} />
            </label>
            <RichTextEditor label="Texto da mensagem" rows={3} value={payment.intro_text ?? ""} variables={vars} onChange={(intro_text) => setPayment({ intro_text })} />
          </div>
        )}
      </div>

      <div className="space-y-2 rounded-xl border border-line-soft p-3">
        <p className="text-sm font-medium text-fg">Como mostrar o Pix</p>
        <p className="text-xs text-muted">Escolha como o lead recebe o Pix.</p>
        <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Como mostrar o Pix">
          {([
            { value: "qr", label: "QR Code", hint: "Imagem com o QR, o texto e o código Pix." },
            { value: "steps", label: "Passo a passo", hint: 'Instruções, o código numa caixa "copy" e os botões.' },
            { value: "both", label: "Ambos", hint: "Envia o QR Code, o passo a passo e o Pix copia e cola." },
          ] as const).map((item) => {
            const active = pixMode === item.value;
            return (
              <button
                aria-checked={active}
                className={`min-h-9 rounded-full border px-4 text-xs font-medium transition ${
                  active ? "border-brand bg-brand text-white" : "border-line bg-well text-fg-2 hover:text-fg"
                }`}
                key={item.value}
                onClick={() => setModes(item.value !== "steps", item.value !== "qr")}
                role="radio"
                type="button"
              >
                {item.label}
              </button>
            );
          })}
        </div>
        <p className="text-xs text-muted">
          {pixMode === "both"
            ? "Envia o QR Code, o passo a passo e o Pix copia e cola, tudo junto."
            : pixMode === "qr"
              ? "Imagem com o QR, o texto e o código Pix."
              : 'Instruções, o código numa caixa "copy" e os botões.'}
        </p>
      </div>
      {qrOn && (
        <RichTextEditor label="Mensagem do Pix (QR Code)" rows={3} value={payment.pix_text} variables={vars} onChange={(pix_text) => setPayment({ pix_text })} />
      )}
      {stepsOn && (
        <>
          <RichTextEditor
            label="Instruções de pagamento (passo a passo)"
            rows={6}
            value={payment.steps_text ?? STEPS_TEXT}
            variables={vars}
            onChange={(steps_text) => setPayment({ steps_text })}
          />
          <Field label="Texto acima do código">
            <input className="field" maxLength={200} value={payment.code_intro ?? "Copie o código abaixo:"} onChange={(event) => setPayment({ code_intro: event.target.value })} />
          </Field>
          {!qrOn && (
            <Field label="Texto junto dos botões">
              <input
                className="field"
                maxLength={500}
                value={payment.after_code_text ?? "Após efetuar o pagamento, clique no botão abaixo ⤵️"}
                onChange={(event) => setPayment({ after_code_text: event.target.value })}
              />
            </Field>
          )}
        </>
      )}
      <div className="space-y-2 rounded-xl border border-line-soft p-3">
        <Switch
          checked={payment.approved_enabled !== false}
          label="Enviar mensagem de pagamento aprovado (antes da entrega)"
          onChange={(on) => setPayment({ approved_enabled: on })}
        />
        {payment.approved_enabled !== false ? (
          <>
            <RichTextEditor label="Mensagem de pagamento aprovado" rows={3} value={payment.approved_text} variables={vars} onChange={(approved_text) => setPayment({ approved_text })} />
            <MediaGrid
              kinds={["photo", "video"]}
              max={3}
              title="Imagem junto da mensagem (opcional)"
              value={payment.approved_media_ids ?? []}
              onChange={(approved_media_ids) => setPayment({ approved_media_ids })}
            />
            {(payment.approved_media_ids?.length ?? 0) > 0 && (
              <label className="flex items-center justify-between gap-3 text-sm text-fg-2">
                <span>Borrar a mídia (spoiler)</span>
                <Switch checked={!!payment.approved_spoiler} label="Borrar a mídia" onChange={(approved_spoiler) => setPayment({ approved_spoiler })} />
              </label>
            )}
            <p className="text-[11px] text-muted">
              Enviada assim que o Pix é pago; logo depois vem a entrega do plano (ou a entrega padrão).
              {(payment.approved_media_ids?.length ?? 0) > 0 && " A imagem vai junto do texto, na mesma mensagem."}
            </p>
            {payment.approved_enabled == null && draft.upsells.length > 0 && (
              <p className="flex flex-wrap items-center gap-2 text-[11px] text-warning">
                Neste funil ela é pulada quando um upsell vem logo depois do pagamento.
                <button className="font-semibold text-accent underline" onClick={() => setPayment({ approved_enabled: true })} type="button">
                  Enviar sempre
                </button>
              </p>
            )}
          </>
        ) : (
          <p className="text-[11px] text-muted">Desligado: assim que o Pix é pago, a entrega vai direto, sem mensagem.</p>
        )}
      </div>
      <RichTextEditor label="Pix expirado" rows={2} value={payment.expired_text} variables={vars} onChange={(expired_text) => setPayment({ expired_text })} />
      <div className="space-y-2 rounded-xl border border-line-soft p-3">
        <Switch
          checked={!!payment.reactivation_enabled}
          label="Reativação automática do Pix"
          onChange={(reactivation_enabled) => setPayment({ reactivation_enabled })}
        />
        <p className="text-xs text-muted">
          Quando o Pix vence, o bot gera e manda um novo sozinho, sem o lead precisar tocar em nada.
        </p>
        {payment.reactivation_enabled && (
          <div className="grid gap-3">
            <Field label="Quantas vezes reativar">
              <select
                className="field"
                value={payment.reactivation_limit ?? 1}
                onChange={(event) => setPayment({ reactivation_limit: Number(event.target.value) })}
              >
                <option value={1}>1 vez</option>
                <option value={2}>2 vezes</option>
                <option value={0}>Ilimitado</option>
              </select>
            </Field>
            <RichTextEditor
              label="Mensagem ao gerar o novo Pix"
              rows={2}
              value={payment.reactivation_text ?? "Seu Pix venceu, mas já gerei um novo pra você 👇 É só pagar com o código abaixo."}
              variables={vars}
              onChange={(reactivation_text) => setPayment({ reactivation_text })}
            />
            <p className="text-[11px] text-muted">Atingido o limite, o lead recebe a mensagem de "Pix expirado" acima com o botão manual.</p>
          </div>
        )}
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Botão copiar">
          <input className="field" maxLength={64} value={payment.copy_button} onChange={(event) => setPayment({ copy_button: event.target.value })} />
        </Field>
        <Field label="Botão verificar">
          <input className="field" maxLength={64} value={payment.check_button} onChange={(event) => setPayment({ check_button: event.target.value })} />
        </Field>
      </div>
      <Field label={`Resposta ao "Já paguei" sem pagamento`}>
        <input className="field" maxLength={200} value={payment.pending_text} onChange={(event) => setPayment({ pending_text: event.target.value })} />
      </Field>
      <MediaGrid
        kinds={["photo", "video"]}
        max={3}
        title={`Imagem ao clicar em "Já paguei" (opcional)`}
        value={payment.pending_media_ids ?? []}
        onChange={(pending_media_ids) => setPayment({ pending_media_ids })}
      />
      {(payment.pending_media_ids?.length ?? 0) > 0 && (
        <label className="flex items-center justify-between gap-3 text-sm text-fg-2">
          <span>Borrar a mídia (spoiler)</span>
          <Switch checked={!!payment.pending_spoiler} label="Borrar a mídia" onChange={(pending_spoiler) => setPayment({ pending_spoiler })} />
        </label>
      )}
      <PaymentRecoveryBlock draft={draft} set={set} vars={vars} />
    </Panel>
  );
}

/** Behavioural trigger: generated a Pix but did not pay within X minutes -> one recovery message
 *  (reminder / objection answered / fresh Pix link), sent automatically. */
function PaymentRecoveryBlock({ draft, set, vars }: Pick<SectionProps, "draft" | "set"> & { vars: string[] }) {
  const recovery: PaymentRecovery = draft.payment_recovery ?? emptyPaymentRecovery();
  const setRecovery = (patch: Partial<PaymentRecovery>) => set({ payment_recovery: { ...recovery, ...patch } });
  return (
    <div className="space-y-2 rounded-xl border border-line-soft p-3">
      <Switch
        checked={!!recovery.enabled}
        label="Recuperação automática (gerou Pix e não pagou)"
        onChange={(enabled) => set({ payment_recovery: { ...emptyPaymentRecovery(), ...recovery, enabled } })}
      />
      <p className="text-xs text-muted">
        Se o lead gera o Pix e não paga, o bot manda sozinho uma mensagem de recuperação depois do tempo abaixo — um lembrete, uma objeção respondida ou um novo link de pagamento.
      </p>
      {recovery.enabled && (
        <div className="space-y-2">
          <Field label="Esperar quantos minutos após gerar o Pix">
            <input
              className="field"
              type="number"
              min={1}
              max={1440}
              value={recovery.delay_minutes}
              onChange={(event) => setRecovery({ delay_minutes: Math.min(1440, Math.max(1, Number(event.target.value) || 15)) })}
            />
          </Field>
          <MediaGrid
            kinds={["photo", "video"]}
            max={3}
            title="Mídia da mensagem (opcional)"
            value={recovery.media_ids ?? []}
            onChange={(media_ids) => setRecovery({ media_ids })}
          />
          {(recovery.media_ids?.length ?? 0) > 0 && (
            <label className="flex items-center justify-between gap-3 text-sm text-fg-2">
              <span>Borrar a mídia (spoiler)</span>
              <Switch checked={!!recovery.spoiler} label="Borrar a mídia" onChange={(spoiler) => setRecovery({ spoiler })} />
            </label>
          )}
          <RichTextEditor label="Mensagem de recuperação" rows={3} value={recovery.text} variables={vars} onChange={(text) => setRecovery({ text })} />
          <label className="flex items-center justify-between gap-3 text-sm text-fg-2">
            <span>Botão "gerar novo Pix"</span>
            <Switch checked={!!recovery.new_pix_button} label="Botão gerar novo Pix" onChange={(new_pix_button) => setRecovery({ new_pix_button })} />
          </label>
          {recovery.new_pix_button && (
            <Field label="Texto do botão">
              <input className="field" maxLength={64} value={recovery.button_label} onChange={(event) => setRecovery({ button_label: event.target.value })} />
            </Field>
          )}
        </div>
      )}
    </div>
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
