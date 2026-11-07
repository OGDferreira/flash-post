import assert from "node:assert/strict";
import test from "node:test";

import { simulate } from "../src/features/bots/simulator/simulate.ts";

const delivery = (text: string) => ({ type: "default" as const, group_chat_id: null, text, media_ids: [], link: null, join_button_label: "Entrar", start_upsell: true });

const flow: any = {
  version: 1,
  age_gate: { enabled: true, text: "Você tem 18+?", button: "Sim, tenho" },
  welcome: [{ type: "text", text: "Oi {nome}!", media_ids: [], spoiler: false, delay_seconds: 2 }],
  offer: {
    text: "Conteúdo exclusivo", media_ids: [], spoiler: false, secondary_enabled: false, secondary_text: "",
    cta_enabled: true, cta_label: "Ver planos", cta_style: "primary", plans_text: "Escolha:", redirect_buttons: [],
  },
  plans: [{ id: "vip", name: "VIP", price: "19.90", duration_days: 30, button_style: "success", delivery: delivery("Acesso {plano}"), bump_mode: "default" }],
  payment: {
    expiration_minutes: 15, pix_text: "Pague {valor} de {plano}", copy_button: "Copiar", check_button: "Já paguei",
    pending_text: "Ainda não caiu", approved_text: "Aprovado!", expired_text: "Expirou",
  },
  default_delivery: null,
  order_bump: { name: "Pack", price: "5.00", text: "Quer {bump} por {bump_valor}?", media_ids: [], accept_label: "Sim", decline_label: "Não", delivery: delivery("Seu pack") },
  upsells: [{ name: "Mais", price: "9.90", duration_days: null, delay_minutes: 0, media_ids: [], spoiler: false, text: "Leva {plano}?", accept_label: "Quero", accept_style: "success", decline_label: "Não", hide_decline: false, delivery: delivery("Upsell entregue") }],
  downsells: [{ delay_minutes: 10, media_ids: [], spoiler: false, text: "{desconto} off", discount_type: "percent", discount_value: "50", plan_ids: [], custom_offer: null, button_style: "danger" }],
  downsells_no_pix: [],
};

const texts = (actions: string[]) => simulate(flow, actions).messages.map((m) => m.text ?? "");

test("age gate, welcome, CTA, plans, bump, Pix, payment, deliveries and upsell", () => {
  const before = simulate(flow, ["start"]);
  assert.equal(before.messages.at(-1)?.buttons?.[0][0].action, "age");
  const run = ["start", "age", "plans", "plan:vip", "bump:y"];
  const atPix = simulate(flow, run);
  assert.ok(atPix.controls.canPay && atPix.controls.canExpire);
  assert.ok(texts(run).includes("Oi Lucas!"));
  assert.ok(texts(run).includes("Quer Pack por R$ 5,00?"));
  assert.ok(texts(run).some((t) => t.startsWith("Pague R$ 24,90 de VIP + Pack")));
  const paid = texts([...run, "pay"]);
  // upsell follows (start_upsell): no approved text; plan delivery, bump delivery, then upsell
  assert.ok(!paid.includes("Aprovado!"));
  assert.ok(paid.includes("Acesso VIP") && paid.includes("Seu pack") && paid.includes("Leva Mais?"));
  const upsold = texts([...run, "pay", "up:y:0", "pay"]);
  assert.ok(upsold.includes("Upsell entregue"));
});

test("unpaid Pix shows the downsell with the discounted price", () => {
  const result = simulate(flow, ["start", "age", "plans", "plan:vip", "bump:n", "expire"]);
  const last = result.messages.at(-1);
  assert.equal(last?.text, "50% off");
  assert.match(last?.buttons?.[0][0].label ?? "", /R\$ 9,95/);
  const again = simulate(flow, ["start", "age", "plans", "plan:vip", "bump:n", "expire", "ds:pix:0:vip"]);
  assert.ok(again.messages.some((m) => (m.text ?? "").startsWith("Pague R$ 9,95")));
});

test("approved text shows when no upsell follows, and the check button answers", () => {
  const noUpsell = { ...flow, upsells: [] };
  const msgs = simulate(noUpsell, ["start", "age", "plans", "plan:vip", "bump:n", "check", "pay"]).messages.map((m) => m.text ?? "");
  assert.ok(msgs.some((t) => t.includes("Ainda não caiu")));
  assert.ok(msgs.includes("Aprovado!") && msgs.includes("Acesso VIP"));
});
