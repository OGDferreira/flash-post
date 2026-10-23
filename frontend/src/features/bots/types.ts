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
  type: "group" | "pack" | "default" | "upsell";
  group_chat_id?: number | null;
  text?: string | null;
  media_ids: string[];
  link?: { label: string; url: string } | null;
  join_button_label: string;
  start_upsell: boolean;
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
  hide_decline: boolean;
  delivery: Delivery | null;
};

export type CustomOffer = {
  name: string;
  price: string;
  duration_days: number | null;
  delivery: Delivery | null;
};

export type DownsellStep = {
  delay_minutes: number;
  media_ids: string[];
  spoiler: boolean;
  text: string;
  discount_type: "percent" | "fixed";
  discount_value: string;
  plan_ids: string[];
  custom_offer: CustomOffer | null;
  button_style: ButtonStyle;
};

export type Previews = {
  enabled: boolean;
  label: string;
  style: ButtonStyle;
  text?: string | null;
  media_ids: string[];
  spoiler: boolean;
  /** Seconds until the preview messages delete themselves (5 s to 48 h). */
  delete_after_seconds: number;
};

export function emptyPreviews(): Previews {
  return { enabled: false, label: "👀 Ver prévias", style: "primary", text: "👀 Prévias liberadas! Elas somem em {tempo}.", media_ids: [], spoiler: false, delete_after_seconds: 60 };
}

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
  previews?: Previews;
  /** Legacy single sequence settings; the server folds them into the two lists below. */
  downsell_trigger?: "pix" | "start";
  downsell_audience?: ("no_pix" | "pix")[] | null;
  /** Generated a PIX and did not pay. */
  downsells: DownsellStep[];
  /** Started and never generated a PIX. */
  downsells_no_pix?: DownsellStep[] | null;
  support_username?: string | null;
};

export type Flow = {
  id: string;
  name: string;
  definition: FlowDefinition;
  version: number;
  bots: number;
  updated_at: string | null;
  shared?: boolean;
  /** null = every partner; otherwise the partner user ids it is shared with. */
  shared_with?: string[] | null;
  shared_loop_id?: string | null;
  from_template?: boolean;
  hidden_by_admin?: boolean; // only the Super Admin, inside the account, ever sees it true
  /** Copy received from a chief: runs in the bot, but its content is never sent here. */
  protected?: boolean;
};

export type Bot = {
  hidden_by_admin?: boolean;
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
  delivery_group_chat_id?: number | null;
  cache_chat_id?: number | null;
};

export type SharedFlowOption = { id: string; name: string; shared_from_chief: true };

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
  return { type, group_chat_id: null, text: "", media_ids: [], link: null, join_button_label: "🔓 Entrar no VIP", start_upsell: true };
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

// ---------------------------------------------------------------- remarketing

export type CampaignTarget = "all" | "not_bought" | "bought" | "pix_generated" | "vip_expired" | "group_members";
export type CampaignPeriod = "total" | "today" | "yesterday" | "7d" | "30d" | "custom";

export type CampaignMessage = { text: string; media_ids: string[]; spoiler: boolean; buttons: LinkButton[] };
export type CampaignPlan = { name: string; price: string; duration_days: number | null; delivery: Delivery | null; button_style: ButtonStyle };

export type CampaignDefinition = {
  audience: { target: CampaignTarget; period: CampaignPeriod; start?: string | null; end?: string | null };
  messages: CampaignMessage[];
  offer: { plans: CampaignPlan[]; order_bump: OrderBump | null; redirect: LinkButton | null };
};

export type Campaign = {
  id: string;
  flow_id: string;
  flow_name: string;
  name: string;
  status: "draft" | "scheduled" | "sending" | "finished" | "paused";
  definition: CampaignDefinition;
  scheduled_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  total: number;
  sent: number;
  failed: number;
  blocked: number;
  already_blocked: number;
  runs: number;
  sales: number;
  revenue: string;
  created_at: string | null;
};

export function emptyCampaignDefinition(): CampaignDefinition {
  return {
    audience: { target: "not_bought", period: "total", start: null, end: null },
    messages: [{ text: "", media_ids: [], spoiler: false, buttons: [] }],
    offer: { plans: [], order_bump: null, redirect: null },
  };
}
