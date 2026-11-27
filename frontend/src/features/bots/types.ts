// Mirrors backend/app/bots/flow_schema.py and the /api/bots responses.

export type BlockType = "text" | "photo" | "video" | "voice" | "video_note" | "album";

export type Block = {
  type: BlockType;
  text?: string | null;
  media_ids: string[];
  spoiler: boolean;
  delay_seconds: number;
  /** Humanized conversation: wait for the lead to reply before sending this block. */
  wait_for_reply?: boolean;
};

export type Delivery = {
  type: "group" | "pack" | "default" | "upsell";
  group_chat_id?: number | null;
  text?: string | null;
  media_ids: string[];
  link?: { label: string; url: string } | null;
  join_button_label: string;
  start_upsell: boolean;
  /** Messages (text/audio) dripped to the buyer after this delivery, for any purchase that
   *  uses it (plan, order bump, upsell or downsell). Each has its own delay_seconds. */
  after_purchase?: Block[];
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
  delivery: Delivery | null; // null = the funnel's default delivery
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
  /** Fixed card price in USD (international "fixed" pricing); empty = convert by the rate. */
  price_usd?: string | null;
  /** Own "payment approved" message; empty/null = use the funnel default. */
  approved_text?: string | null;
};

/** Per-funnel card/international settings (Stripe). ``enabled`` only takes effect when the
 *  "Vendas Internacionais" gateway is live. */
export type International = {
  enabled: boolean;
  currencies: "USD"[];
  pricing: "variable" | "fixed";
  usd_rate: string;
  translate: boolean;
};

export function emptyInternational(): International {
  return { enabled: false, currencies: [], pricing: "variable", usd_rate: "5.00", translate: false };
}

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
  /** Own "payment approved" message; empty/null = use the funnel default. */
  approved_text?: string | null;
};

export type CustomOffer = {
  name: string;
  price: string;
  duration_days: number | null;
  delivery: Delivery | null;
  /** Own "payment approved" message; empty/null = use the funnel default. */
  approved_text?: string | null;
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

export type GroupPreview = {
  enabled: boolean;
  label: string;
  style: ButtonStyle;
  group_chat_id: number | null;
  /** Seconds the lead keeps access before the bot removes them (10 s to 24 h). */
  access_seconds: number;
  grant_text?: string | null;
  join_label: string;
  expired_text: string;
};

export function emptyGroupPreview(): GroupPreview {
  return {
    enabled: false, label: "🎁 Entrar grátis no grupo", style: "success", group_chat_id: null, access_seconds: 300,
    grant_text: "✅ Liberado! Você tem {tempo} de acesso ao grupo. Entre agora 👇", join_label: "🔓 Entrar no grupo",
    expired_text: "⏰ Seu acesso à prévia do grupo acabou!\n\nGaranta o acesso completo agora 👇",
  };
}

export type Mimo = {
  enabled: boolean;
  label: string;
  style: ButtonStyle;
  prompt_text: string;
  min_amount: string;
  max_amount: string;
  invalid_text: string;
  thanks_text: string;
};

export function emptyMimo(): Mimo {
  return {
    enabled: false, label: "🎁 Mandar um mimo", style: "primary",
    prompt_text: "Que carinho! 🥰 Digite o valor do seu mimo em reais (ex: 20):",
    min_amount: "5.00", max_amount: "5000.00",
    invalid_text: "Envie só o valor em reais, entre {min} e {max}. Ex: 20 ou 19,90.",
    thanks_text: "Recebido! 🥰 Muito obrigada pelo mimo de {valor}. Você é especial 💖",
  };
}

export type PaymentRecovery = {
  enabled: boolean;
  delay_minutes: number;
  text: string;
  media_ids: string[];
  spoiler: boolean;
  new_pix_button: boolean;
  button_label: string;
};

export function emptyPaymentRecovery(): PaymentRecovery {
  return {
    enabled: false,
    delay_minutes: 15,
    text: "Vi que você gerou o Pix mas ainda não finalizou 👀\nQualquer dúvida é só me chamar. Quer que eu gere um novo Pix pra você?",
    media_ids: [],
    spoiler: false,
    new_pix_button: true,
    button_label: "💠 Gerar um novo Pix",
  };
}

export type SmartThen = "none" | "plans" | "offer";

export type SmartReplyRule = {
  keywords: string[];
  reply: string;
  then: SmartThen;
};

export type SmartReplies = {
  enabled: boolean;
  rules: SmartReplyRule[];
  fallback_enabled: boolean;
  fallback_text: string;
  fallback_then: SmartThen;
};

export function emptySmartReplies(): SmartReplies {
  return {
    enabled: false,
    rules: [],
    fallback_enabled: false,
    fallback_text: "Não entendi 😅 Toque em um dos botões acima para continuar, ou me diga o que você procura.",
    fallback_then: "none",
  };
}

export type FollowUpStep = {
  delay_minutes: number;
  text?: string | null;
  media_ids: string[];
  spoiler: boolean;
};

export type FollowUp = {
  enabled: boolean;
  steps: FollowUpStep[];
};

export function emptyFollowUp(): FollowUp {
  return { enabled: false, steps: [] };
}

export type FlowDefinition = {
  version: 1;
  age_gate: { enabled: boolean; text: string; button: string };
  international?: International;
  /** "Conversa humanizada" master switch for the welcome sequence (default on). */
  welcome_enabled?: boolean;
  welcome: Block[];
  offer: Offer;
  /** Keyword replies + fallback for leads who type something off-script in the DM. */
  smart_replies?: SmartReplies;
  /** Follow-ups automáticos quando o lead some no meio do funil (retomada de conversa). */
  follow_up?: FollowUp;
  plans: Plan[];
  payment: {
    expiration_minutes: number;
    pix_text: string;
    copy_button: string;
    check_button: string;
    pending_text: string;
    approved_text: string;
    /** true: always send before the delivery; false: never; null/undefined: old rule
     *  (skipped when an upsell follows). */
    approved_enabled?: boolean | null;
    /** Optional image sent with the "payment approved" message (media + caption, same message). */
    approved_media_ids?: string[];
    approved_spoiler?: boolean;
    expired_text: string;
    /** Legacy single choice; folded on load into qr_enabled/steps_enabled. */
    layout?: "qr" | "steps";
    /** Both can be on at the same time. null/undefined on both = derive from layout. */
    qr_enabled?: boolean | null;
    steps_enabled?: boolean | null;
    steps_text?: string;
    code_intro?: string;
    after_code_text?: string;
    /** Optional message (media + text) sent right before the Pix. */
    intro_enabled?: boolean;
    intro_text?: string | null;
    intro_media_ids?: string[];
    intro_spoiler?: boolean;
  };
  /** Behavioural trigger: generated a Pix but did not pay within delay_minutes -> recovery nudge. */
  payment_recovery?: PaymentRecovery;
  default_delivery?: Delivery | null;
  order_bump?: OrderBump | null;
  upsells: UpsellStep[];
  previews?: Previews;
  group_preview?: GroupPreview;
  mimo?: Mimo;
  /** Legacy single sequence settings; the server folds them into the two lists below. */
  downsell_trigger?: "pix" | "start";
  downsell_audience?: ("no_pix" | "pix")[] | null;
  /** Generated a PIX and did not pay. */
  downsells: DownsellStep[];
  /** Started and never generated a PIX. */
  downsells_no_pix?: DownsellStep[] | null;
  support_username?: string | null;
  /** @ do bot no Telegram mostrado no teste do funil (abre t.me/<@>). */
  bot_handle?: string | null;
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
  taken_from?: string | null; // the user's operation this bot was taken over from (Super Admin only)
  id: string;
  username: string;
  name: string;
  flow_id: string | null;
  folder_id: string | null;
  ab_test_id?: string | null;
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
  lead_id: string;
  source: string | null;
  created_at: string | null;
  paid_at: string | null;
};

export type LeadAudience = "all" | "paid" | "pix_unpaid" | "no_pix";

export type BotLead = {
  id: string;
  name: string;
  username: string | null;
  bot: string;
  has_pix: boolean;
  paid: boolean;
  blocked: boolean;
  stage: string;
  created_at: string | null;
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

// ---------------------------------------------------------------- live chat

export type Conversation = {
  lead_id: string;
  name: string;
  username: string | null;
  bot: string;
  unread: number;
  blocked: boolean;
  last_at: string | null;
  last_preview: string;
};

export type ChatMessage = {
  id: string;
  direction: "in" | "out";
  kind: "text" | "photo" | "video" | "audio" | "voice" | "video_note" | "document" | "sticker" | "other";
  text: string | null;
  from_operator: boolean;
  has_media: boolean;
  media_id: string | null;
  created_at: string | null;
};

export type ConversationOrder = {
  id: string;
  kind: string;
  name: string;
  amount: string;
  status: "pending" | "paid" | "expired" | "review" | "failed";
  pix: string | null;
  created_at: string | null;
  paid_at: string | null;
};

export type ConversationDetail = {
  lead: { id: string; name: string; username: string | null; bot: string | null; blocked: boolean; stage: string };
  orders: ConversationOrder[];
  pix_generated: number;
  pix_paid: number;
  messages: ChatMessage[];
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
/** An existing funnel plan re-offered at a discount in the campaign. */
export type CampaignDiscountedPlan = {
  plan_id: string;
  discount_type: "percent" | "fixed";
  discount_value: string;
  button_style: ButtonStyle;
};

export type CampaignDefinition = {
  audience: { target: CampaignTarget; period: CampaignPeriod; start?: string | null; end?: string | null };
  messages: CampaignMessage[];
  offer: { plans: CampaignPlan[]; discounted_plans?: CampaignDiscountedPlan[]; order_bump: OrderBump | null; redirect: LinkButton | null };
};

export type RecurrenceKind = "daily" | "hours" | "weekdays";
/** How a campaign repeats (null = one-shot). `time` is HH:MM BRT; weekdays 0=Mon..6=Sun. */
export type Recurrence = { kind: RecurrenceKind; time: string; hours: number; weekdays: number[] };

export type CampaignRun = {
  id: string;
  started_at: string | null;
  finished_at: string | null;
  status: string;
  total: number;
  sent: number;
  failed: number;
  blocked: number;
  already_blocked: number;
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
  recurrence: Recurrence | null;
  last_run_at: string | null;
  total: number;
  sent: number;
  failed: number;
  blocked: number;
  already_blocked: number;
  runs: number;
  sales: number;
  revenue: string;
  conflicts: { id: string; name: string }[];
  created_at: string | null;
};

export function emptyCampaignDefinition(): CampaignDefinition {
  return {
    audience: { target: "not_bought", period: "total", start: null, end: null },
    messages: [{ text: "", media_ids: [], spoiler: false, buttons: [] }],
    offer: { plans: [], discounted_plans: [], order_bump: null, redirect: null },
  };
}

export type AbVariantMetrics = {
  flow_id: string;
  leads: number;
  pix: number;
  sales: number;
  buyers: number;
  revenue: string;
  conversion: number;
};

export type AbTest = {
  id: string;
  name: string;
  bot_id: string;
  bot_username: string | null;
  status: "active" | "stopped";
  weight_a: number;
  flow_a: { id: string; name: string };
  flow_b: { id: string; name: string };
  created_at: string | null;
  stopped_at: string | null;
  results?: { a: AbVariantMetrics; b: AbVariantMetrics };
};
