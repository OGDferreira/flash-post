// Mirrors backend/app/bots/flow_schema.py and the /api/bots responses.

export type BlockType = "text" | "photo" | "video" | "voice" | "video_note" | "album";

export type Block = {
  type: BlockType;
  text?: string | null;
  media_ids: string[];
  spoiler: boolean;
  delay_seconds: number;
};

export type Delivery = {
  type: "group" | "pack" | "default";
  group_chat_id?: number | null;
  text?: string | null;
  media_ids: string[];
  link?: { label: string; url: string } | null;
  join_button_label: string;
};

export type ButtonStyle = "default" | "primary" | "success" | "danger";
export type LinkButton = { label: string; url: string };

export type OrderBump = {
  name: string;
  price: string;
  text: string;
  media_ids: string[];
  accept_label: string;
  decline_label: string;
  delivery: Delivery;
};

export type Plan = {
  id: string;
  name: string;
  price: string;
  duration_days: number | null;
  button_text?: string | null;
  button_style: ButtonStyle;
  delivery?: Delivery | null;
  bump_mode: "default" | "custom" | "off";
  order_bump?: OrderBump | null;
};

export type Offer = {
  text: string;
  media_ids: string[];
  spoiler: boolean;
  secondary_enabled: boolean;
  secondary_text: string;
  cta_enabled: boolean;
  cta_label: string;
  cta_style: ButtonStyle;
  plans_text: string;
  redirect_buttons: LinkButton[];
};

export type UpsellStep = {
  name: string;
  price: string;
  duration_days: number | null;
  delay_minutes: number;
  media_ids: string[];
  spoiler: boolean;
  text: string;
  accept_label: string;
  accept_style: ButtonStyle;
  decline_label: string;
  delivery: Delivery;
};

export type DownsellStep = {
  delay_minutes: number;
  media_ids: string[];
  spoiler: boolean;
  text: string;
  discount_type: "percent" | "fixed";
  discount_value: string;
  plan_ids: string[];
  button_style: ButtonStyle;
};

export type FlowDefinition = {
  version: 1;
  age_gate: { enabled: boolean; text: string; button: string };
  welcome: Block[];
  offer: Offer;
  plans: Plan[];
  payment: {
    expiration_minutes: number;
    pix_text: string;
    copy_button: string;
    check_button: string;
    pending_text: string;
    approved_text: string;
    expired_text: string;
  };
  default_delivery?: Delivery | null;
  order_bump?: OrderBump | null;
  upsells: UpsellStep[];
  downsell_trigger: "pix" | "start";
  downsells: DownsellStep[];
  support_username?: string | null;
};

export type Flow = {
  id: string;
  name: string;
  definition: FlowDefinition;
  version: number;
  bots: number;
  updated_at: string | null;
};

export type Bot = {
  id: string;
  username: string;
  name: string;
  flow_id: string | null;
  is_active: boolean;
  status: string;
  last_error: string | null;
  created_at: string | null;
  leads: number;
  sales: number;
  revenue: string;
};

export type BotGroup = {
  chat_id: number;
  title: string;
  type: string;
  can_invite: boolean;
  bot: string;
};

export type BotMedia = {
  id: string;
  kind: "photo" | "video" | "audio";
  file_name: string;
  content_type: string;
  size_bytes: number;
};

export type BotOrder = {
  id: string;
  status: "pending" | "paid" | "expired" | "review" | "failed";
  plan: string;
  amount: string;
  net_amount: string | null;
  bot: string;
  lead: string | null;
  lead_username: string | null;
  source: string | null;
  created_at: string | null;
  paid_at: string | null;
};

export type BotsSummary = {
  days: number;
  leads: number;
  pix_generated: number;
  pix_paid: number;
  revenue: string;
  conversion: number;
};

export type BotsConfig = {
  smokepay_configured: boolean;
  smokepay_webhook_configured: boolean;
  payment_webhook_url: string;
};

export function brl(value: string | number) {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(Number(value));
}

export function emptyDelivery(type: Delivery["type"] = "default"): Delivery {
  return { type, group_chat_id: null, text: "", media_ids: [], link: null, join_button_label: "🔓 Entrar no VIP" };
}

export type FlowSummary = { leads: number; vips: number; revenue: string };

export function emptyBump(): OrderBump {
  return {
    name: "Pack extra",
    price: "9.90",
    text: "Quer adicionar <b>{bump}</b> por apenas <b>+{bump_valor}</b>?",
    media_ids: [],
    accept_label: "✅ Sim, quero!",
    decline_label: "Não, obrigado",
    delivery: emptyDelivery("pack"),
  };
}
