import { useState } from "react";
import { Copy, CreditCard, Gift, Plus, ShieldCheck, ShoppingCart, Trash2, TrendingDown, TrendingUp, Truck } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { brl, emptyBump, emptyDelivery, type CustomOffer, type Delivery, type DownsellStep, type Plan, type UpsellStep } from "../types";
import { BumpEditor, DeliveryEditor } from "./DeliveryEditor";
import { MediaGrid } from "./MediaGrid";
import { BASE_VARIABLES, RichTextEditor } from "./RichTextEditor";
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
      <Field label="Texto do botão (opcional)" hint="Vazio = “Nome · Preço”.">
        <input className="field" maxLength={64} value={plan.button_text ?? ""} onChange={(event) => set({ button_text: event.target.value })} />
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
    <Panel
      icon={<CreditCard size={18} />}
      title="Planos de pagamento"
      description="Cada plano vira um botão. O mínimo do Pix é R$ 1,00."
      aside={<span className="text-xs text-muted">{draft.plans.length}/10</span>}
    >
      <div className="space-y-2">
        {draft.plans.map((plan, index) => (
          <Collapsible
            key={plan.id}
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
        ))}
      </div>
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
            subtitle={`${brl(step.price || 0)} · ${delayLabel(step.delay_minutes)}`}
            actions={
              <StepActions
                canCopy={draft.upsells.length < 20}
                onCopy={() => set({ upsells: [...draft.upsells, { ...step }] })}
                onRemove={() => set({ upsells: draft.upsells.filter((_, i) => i !== index) })}
              />
            }
          >
            <MediaGrid max={3} value={step.media_ids} onChange={(media_ids) => setStep(index, { media_ids })} />
            <Field label={index === 0 ? "Enviar (depois do pagamento)" : "Enviar (depois da resposta anterior)"}>
              <DelayInput value={step.delay_minutes} onChange={(delay_minutes) => setStep(index, { delay_minutes })} />
            </Field>
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
                <span className="block text-xs text-muted">Sem o “não”, a próxima oferta vai sozinha depois do tempo dela.</span>
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

export function DownsellSection({ draft, set }: SectionProps) {
  const { open, toggle, setOpen } = useOpen();
  const setStep = (index: number, patch: Partial<DownsellStep>) =>
    set({ downsells: draft.downsells.map((item, i) => (i === index ? { ...item, ...patch } : item)) });
  return (
    <Panel
      icon={<TrendingDown size={18} />}
      title="Sequências de downsell"
      description="Planos com desconto para quem não pagou. Para sozinho assim que o lead paga."
      aside={<span className="text-xs text-muted">{draft.downsells.length}/20</span>}
    >
      <div className="grid gap-1.5 text-sm text-fg-2">
        <span>Enviar para</span>
        <div className="grid grid-cols-2 gap-2">
          {(
            [
              ["no_pix", "Pix não gerado", "deu /start e não gerou Pix"],
              ["pix", "Pix gerado", "gerou o Pix e não pagou"],
            ] as const
          ).map(([value, label, hint]) => {
            const on = draft.downsell_audience.includes(value);
            return (
              <button
                aria-pressed={on}
                className={`rounded-xl border p-3 text-left transition ${on ? "border-brand bg-brand-soft" : "border-line bg-surface-inset opacity-70"}`}
                key={value}
                onClick={() =>
                  set({ downsell_audience: on ? draft.downsell_audience.filter((item) => item !== value) : [...draft.downsell_audience, value] })
                }
                type="button"
              >
                <span className={`block text-sm font-medium ${on ? "text-accent" : "text-fg"}`}>{on ? "✓ " : ""}{label}</span>
                <span className="block text-xs text-muted">{hint}</span>
              </button>
            );
          })}
        </div>
        {draft.downsell_audience.length === 0 && <span className="text-xs text-warning">Nenhum público marcado: o downsell não será enviado.</span>}
      </div>
      <div className="space-y-2">
        {draft.downsells.map((step, index) => (
          <Collapsible
            key={index}
            open={open === index}
            onToggle={() => toggle(index)}
            title={`Sequência ${index + 1}`}
            subtitle={`${
              step.custom_offer
                ? `${step.custom_offer.name} · ${brl(step.custom_offer.price || 0)}`
                : `${step.discount_type === "percent" ? `${Number(step.discount_value)}%` : brl(step.discount_value || 0)} off`
            } · ${delayLabel(step.delay_minutes)}`}
            actions={
              <StepActions
                canCopy={draft.downsells.length < 20}
                onCopy={() => set({ downsells: [...draft.downsells, { ...step }] })}
                onRemove={() => set({ downsells: draft.downsells.filter((_, i) => i !== index) })}
              />
            }
          >
            <MediaGrid max={3} value={step.media_ids} onChange={(media_ids) => setStep(index, { media_ids })} />
            <Field label={index === 0 ? "Enviar depois de" : "Enviar depois da sequência anterior"}>
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
                {draft.plans.map((plan) => {
                  const on = step.plan_ids.length === 0 || step.plan_ids.includes(plan.id);
                  return (
                    <button
                      aria-pressed={on}
                      className={`min-h-9 rounded-full border px-3 text-xs ${on ? "border-brand bg-brand-soft text-accent" : "border-line text-muted"}`}
                      key={plan.id}
                      onClick={() => {
                        const current = step.plan_ids.length ? step.plan_ids : draft.plans.map((p) => p.id);
                        const next = on ? current.filter((id) => id !== plan.id) : [...current, plan.id];
                        setStep(index, { plan_ids: next.length === draft.plans.length ? [] : next });
                      }}
                      type="button"
                    >
                      {plan.name}
                    </button>
                  );
                })}
                {draft.plans.length === 0 && <span className="text-xs text-muted">Crie planos na seção Planos.</span>}
              </div>
            </div>
            )}
            <StylePicker value={step.button_style} onChange={(button_style) => setStep(index, { button_style })} />
          </Collapsible>
        ))}
      </div>
      <Button
        disabled={draft.downsells.length >= 20}
        onClick={() => {
          set({ downsells: [...draft.downsells, newDownsell(draft.downsells.length)] });
          setOpen(draft.downsells.length);
        }}
        size="sm"
      >
        <Plus size={14} /> Adicionar sequência
      </Button>
    </Panel>
  );
}

// ---------------------------------------------------------------- Entrega, Pagamento, Configurações

export function DeliverySection({ draft, set }: SectionProps) {
  return (
    <Panel
      icon={<Truck size={18} />}
      title="Entrega padrão"
      description="Usada pelos planos que não têm entrega própria."
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
