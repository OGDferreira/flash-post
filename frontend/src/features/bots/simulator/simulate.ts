/**
 * Funnel simulator: replays the taps made in the test panel over the funnel being edited
 * and returns the chat the lead would see. Pure (no network): nothing is charged, no Pix is
 * created and nothing reaches Telegram. Replaying the taps on every render keeps the preview
 * live — edit a text and the bubble changes at once.
 *
 * It follows the bot engine (backend/app/bots/engine.py): age gate → welcome blocks → offer
 * (CTA button or plan buttons, previews, links) → plans → order bump → Pix ("qr" or "steps")
 * → payment → approved text, delivery (plan, then the bump's) → upsells; and the downsells of
 * a Pix not paid / of a lead who never generated one.
 */
import type { ButtonStyle, Delivery, DownsellStep, FlowDefinition, OrderBump, Plan } from "../types";

export type SimButton = { label: string; style?: ButtonStyle; action?: string; url?: string; copy?: boolean };
export type SimMessage = {
  from: "bot" | "user" | "note";
  text?: string;
  media?: string[];
  spoiler?: boolean;
  buttons?: SimButton[][];
  qr?: boolean;
  code?: string;
};
export type SimControls = { canPay: boolean; canExpire: boolean; canSkipNoPix: boolean; started: boolean };
export type SimResult = { messages: SimMessage[]; controls: SimControls };

type Order = {
  name: string;
  /** The plan alone (what deliveries call {plano}); ``name`` adds the bump, like the Pix. */
  planName?: string;
  amount: number;
  delivery: Delivery | null;
  bump: OrderBump | null;
  kind: "plan" | "upsell" | "downsell";
  upsellIndex?: number;
};

export const SIM_PIX_CODE =
  "00020126580014BR.GOV.BCB.PIX0136simulacao-teste-do-funil-sem-cobranca5204000053039865802BR5915FLASH SIMULACAO6009SAO PAULO6304ABCD";

// Same look as the bot ("R$ 19,90", a plain space).
const brl = (value: number) => value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" }).replace(/\s/g, " ");
const money = (value: string | number | null | undefined) => Math.max(0, Number(value) || 0);

function greeting(now = new Date()) {
  const hour = now.getHours();
  return hour < 12 ? "Bom dia" : hour < 18 ? "Boa tarde" : "Boa noite";
}

const BASE_VARS: Record<string, string> = {
  "{nome}": "Lucas",
  "{username}": "@lucas",
  "{bot.nome}": "Seu bot",
  "{bot.username}": "@seu_bot",
};

export function fill(text: string | null | undefined, extra: Record<string, string> = {}): string {
  if (!text) return "";
  let out = text;
  for (const [key, value] of Object.entries({ ...BASE_VARS, "{saudacao}": greeting(), ...extra })) {
    out = out.split(key).join(value);
  }
  return out;
}

export function discounted(price: string, step: DownsellStep): number {
  const base = money(price);
  const value = money(step.discount_value);
  const out = step.discount_type === "percent" ? base * (1 - value / 100) : base - value;
  return Math.max(0.01, Math.round(out * 100) / 100);
}

function bumpFor(flow: FlowDefinition, plan: Plan): OrderBump | null {
  if (plan.bump_mode === "off") return null;
  if (plan.bump_mode === "custom") return plan.order_bump ?? null;
  return flow.order_bump ?? null;
}

const minutes = (value: number) =>
  value >= 60 && value % 60 === 0 ? `${value / 60} h` : `${value} min`;

export function simulate(flow: FlowDefinition, actions: string[]): SimResult {
  const messages: SimMessage[] = [];
  // One holder, so the inner helpers and the loop see the same state.
  const st: {
    order: Order | null;
    stage: "idle" | "age" | "offer" | "bump" | "pix" | "paid" | "done";
    bumpPlan: Plan | null;
    generated: boolean;
  } = { order: null, stage: "idle", bumpPlan: null, generated: false };

  const bot = (message: Omit<SimMessage, "from">) => messages.push({ from: "bot", ...message });
  const user = (text: string) => messages.push({ from: "user", text });
  const note = (text: string) => messages.push({ from: "note", text });
  const support = (): SimButton[][] =>
    flow.support_username ? [[{ label: "💬 Suporte", url: `https://t.me/${flow.support_username.replace(/^@/, "")}` }]] : [];

  const planButtons = (): SimButton[][] =>
    flow.plans.map((plan) => [
      { label: plan.button_text || `${plan.name} · ${brl(money(plan.price))}`, style: plan.button_style, action: `plan:${plan.id}` },
    ]);

  const offer = () => {
    const o = flow.offer;
    let keyboard: SimButton[][] =
      o.cta_enabled && flow.plans.length ? [[{ label: o.cta_label, style: o.cta_style, action: "plans" }]] : planButtons();
    if (flow.previews?.enabled && flow.previews.media_ids.length) {
      keyboard = [...keyboard, [{ label: flow.previews.label, style: flow.previews.style, action: "prev" }]];
    }
    keyboard = [...keyboard, ...o.redirect_buttons.map((b) => [{ label: b.label, url: b.url }]), ...support()];
    const text = fill(o.text);
    if (o.secondary_enabled) {
      bot({ text, media: o.media_ids, spoiler: o.spoiler });
      if (keyboard.length) bot({ text: fill(o.secondary_text) || "👇", buttons: keyboard });
    } else {
      bot({ text: text || (keyboard.length ? fill(o.plans_text) : ""), media: o.media_ids, spoiler: o.spoiler, buttons: keyboard });
    }
    st.stage = "offer";
  };

  const welcome = () => {
    for (const block of flow.welcome) {
      if (block.delay_seconds > 0) note(`⏱ ${block.delay_seconds}s depois`);
      bot({ text: fill(block.text), media: block.media_ids, spoiler: block.spoiler });
    }
    offer();
  };

  const pix = (next: Order) => {
    st.order = next;
    st.stage = "pix";
    st.generated = true;
    const vars = { "{plano}": next.name, "{valor}": brl(next.amount) };
    const p = flow.payment;
    if (p.layout === "steps") {
      const steps = fill(p.steps_text, vars);
      if (steps) bot({ text: steps });
      bot({ text: p.code_intro || "", code: SIM_PIX_CODE });
      bot({
        text: fill(p.after_code_text, vars) || "👇",
        buttons: [[{ label: p.check_button, action: "check" }], [{ label: p.copy_button, copy: true }], ...support()],
      });
    } else {
      bot({
        qr: true,
        text: fill(p.pix_text, vars),
        code: SIM_PIX_CODE,
        buttons: [[{ label: p.copy_button, copy: true }], [{ label: p.check_button, action: "check" }], ...support()],
      });
    }
  };

  const deliver = (delivery: Delivery | null | undefined, name: string, amount: number) => {
    if (!delivery || delivery.type === "upsell") return;
    note(`📦 Entrega de “${name}”`);
    const text = fill(delivery.text, { "{plano}": name, "{valor}": brl(amount) });
    if (delivery.type === "group") {
      bot({
        text: text || "🔓 Seu acesso foi liberado!",
        buttons: [[{ label: delivery.join_button_label || "🔓 Entrar no VIP", url: "https://t.me/+convite-do-grupo" }]],
      });
      return;
    }
    if (text) bot({ text });
    if (delivery.media_ids.length) bot({ media: delivery.media_ids });
    if (delivery.link) bot({ text: delivery.link.label, buttons: [[{ label: delivery.link.label, url: delivery.link.url }]] });
    if (!text && !delivery.media_ids.length && !delivery.link) note("⚠️ Esta entrega está vazia: nada seria enviado.");
  };

  const upsell = (index: number) => {
    const step = flow.upsells[index];
    if (!step) {
      st.stage = "done";
      return;
    }
    note(`🔁 Upsell ${index + 1}${step.delay_minutes ? ` (${minutes(step.delay_minutes)} depois)` : ""}`);
    const buttons: SimButton[][] = [[{ label: step.accept_label, style: step.accept_style, action: `up:y:${index}` }]];
    if (!step.hide_decline) buttons.push([{ label: step.decline_label, action: `up:n:${index}` }]);
    bot({ text: fill(step.text, { "{plano}": step.name, "{valor}": brl(money(step.price)) }), media: step.media_ids, spoiler: step.spoiler, buttons });
    st.stage = "offer";
  };

  const paid = (current: Order) => {
    st.stage = "paid";
    note("✅ Pagamento simulado aprovado");
    const delivery = current.delivery ?? flow.default_delivery ?? null;
    if (current.kind === "upsell") {
      deliver(delivery, current.name, current.amount);
      upsell((current.upsellIndex ?? 0) + 1);
      return;
    }
    const upsellNext = flow.upsells.length > 0 && (!delivery || delivery.type === "upsell" || delivery.start_upsell);
    if (!upsellNext) bot({ text: fill(flow.payment.approved_text, { "{plano}": current.name, "{valor}": brl(current.amount) }) });
    deliver(delivery, current.planName ?? current.name, current.amount);
    if (current.bump) {
      const bumpDelivery = current.bump.delivery ?? flow.default_delivery ?? null;
      if (!(current.bump.delivery == null && bumpDelivery === delivery)) deliver(bumpDelivery, current.bump.name, money(current.bump.price));
    }
    if (upsellNext) upsell(0);
    else st.stage = "done";
  };

  const downsells = (sequence: "pix" | "no_pix") => {
    const steps = (sequence === "pix" ? flow.downsells : flow.downsells_no_pix) ?? [];
    if (!steps.length) {
      note(sequence === "pix" ? "Sem downsells para Pix não pago." : "Sem downsells para quem não gerou Pix.");
      return;
    }
    steps.forEach((step, index) => {
      note(`🏷️ Downsell ${index + 1} · ${minutes(step.delay_minutes)} depois`);
      const off = step.discount_type === "percent" ? `${money(step.discount_value)}%` : brl(money(step.discount_value));
      let buttons: SimButton[][];
      if (step.custom_offer) {
        buttons = [[{ label: `🔥 ${step.custom_offer.name} · ${brl(money(step.custom_offer.price))}`, style: step.button_style, action: `ds:${sequence}:${index}:@` }]];
      } else {
        buttons = flow.plans
          .filter((plan) => !step.plan_ids.length || step.plan_ids.includes(plan.id))
          .map((plan) => [
            {
              label: `🔥 ${plan.name} por ${brl(discounted(plan.price, step))} (antes ${brl(money(plan.price))})`,
              style: step.button_style,
              action: `ds:${sequence}:${index}:${plan.id}`,
            },
          ]);
      }
      bot({ text: fill(step.text, { "{desconto}": off }), media: step.media_ids, spoiler: step.spoiler, buttons });
    });
    st.stage = "offer";
  };

  const labelOf = (action: string): string => {
    for (const message of messages) {
      for (const row of message.buttons ?? []) for (const b of row) if (b.action === action) return b.label;
    }
    return action;
  };

  for (const action of actions) {
    if (action === "start") {
      user("/start");
      if (flow.age_gate.enabled) {
        bot({ text: fill(flow.age_gate.text), buttons: [[{ label: flow.age_gate.button, action: "age" }]] });
        st.stage = "age";
      } else welcome();
    } else if (action === "age") {
      user(labelOf(action));
      welcome();
    } else if (action === "plans") {
      user(labelOf(action));
      bot({ text: fill(flow.offer.plans_text) || "👇", buttons: planButtons() });
    } else if (action === "prev") {
      user(labelOf(action));
      const pv = flow.previews;
      if (pv) {
        bot({ media: pv.media_ids, spoiler: pv.spoiler, text: fill(pv.text, { "{tempo}": `${pv.delete_after_seconds}s` }) });
        note(`🗑️ As prévias somem sozinhas depois de ${pv.delete_after_seconds}s`);
      }
    } else if (action.startsWith("plan:")) {
      user(labelOf(action));
      const plan = flow.plans.find((item) => item.id === action.slice(5));
      if (!plan) continue;
      const bump = bumpFor(flow, plan);
      if (bump) {
        st.bumpPlan = plan;
        st.stage = "bump";
        bot({
          text: fill(bump.text, { "{plano}": plan.name, "{valor}": brl(money(plan.price)), "{bump}": bump.name, "{bump_valor}": brl(money(bump.price)) }),
          media: bump.media_ids,
          buttons: [[{ label: bump.accept_label, action: "bump:y" }], [{ label: bump.decline_label, action: "bump:n" }]],
        });
      } else {
        pix({ name: plan.name, amount: money(plan.price), delivery: plan.delivery ?? null, bump: null, kind: "plan" });
      }
    } else if ((action === "bump:y" || action === "bump:n") && st.bumpPlan) {
      user(labelOf(action));
      const plan = st.bumpPlan;
      const bump = action === "bump:y" ? bumpFor(flow, plan) : null;
      pix({
        name: bump ? `${plan.name} + ${bump.name}` : plan.name,
        planName: plan.name,
        amount: money(plan.price) + (bump ? money(bump.price) : 0),
        delivery: plan.delivery ?? null,
        bump,
        kind: "plan",
      });
      st.bumpPlan = null;
    } else if (action === "check") {
      user(labelOf(action));
      note(`Aviso do Telegram: “${flow.payment.pending_text}”`);
    } else if (action === "pay" && st.order && st.stage === "pix") {
      paid(st.order);
    } else if (action === "expire" && st.order && st.stage === "pix") {
      note(`⌛ ${flow.payment.expiration_minutes} min sem pagar: o Pix expirou`);
      if (flow.payment.expired_text) bot({ text: fill(flow.payment.expired_text) });
      st.order = null;
      downsells("pix");
    } else if (action === "nopix") {
      note("Simulação: o lead não gerou Pix");
      downsells("no_pix");
    } else if (action.startsWith("up:")) {
      user(labelOf(action));
      const [, answer, raw] = action.split(":");
      const index = Number(raw);
      const step = flow.upsells[index];
      if (!step) continue;
      if (answer === "y") {
        pix({ name: step.name, amount: money(step.price), delivery: step.delivery ?? null, bump: null, kind: "upsell", upsellIndex: index });
      } else upsell(index + 1);
    } else if (action.startsWith("ds:")) {
      user(labelOf(action));
      const [, sequence, raw, planId] = action.split(":");
      const step = (sequence === "pix" ? flow.downsells : flow.downsells_no_pix ?? [])[Number(raw)];
      if (!step) continue;
      if (planId === "@" && step.custom_offer) {
        const offerItem = step.custom_offer;
        pix({ name: offerItem.name, amount: money(offerItem.price), delivery: offerItem.delivery, bump: null, kind: "downsell" });
      } else {
        const plan = flow.plans.find((item) => item.id === planId);
        if (plan) pix({ name: plan.name, amount: discounted(plan.price, step), delivery: plan.delivery ?? null, bump: null, kind: "downsell" });
      }
    }
  }

  return {
    messages,
    controls: {
      started: actions.length > 0,
      canPay: st.stage === "pix",
      canExpire: st.stage === "pix",
      canSkipNoPix: st.stage === "offer" && !st.generated && Boolean(flow.downsells_no_pix?.length),
    },
  };
}
