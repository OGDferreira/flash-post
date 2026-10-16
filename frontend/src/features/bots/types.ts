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

export type Plan = {
  id: string;
  name: string;
  price: string;
  duration_days: number | null;
  button_text?: string | null;
  delivery?: Delivery | null;
};

export type FlowDefinition = {
  version: 1;
  age_gate: { enabled: boolean; text: string; button: string };
  welcome: Block[];
  offer: { text: string; media_id?: string | null };
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
