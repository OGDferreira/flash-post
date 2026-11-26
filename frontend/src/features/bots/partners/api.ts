import { apiRequest } from "@/services/api";
import { periodParams, type MetricsPeriod } from "@/features/analytics/period";

export type PartnerUser = {
  id: string;
  name: string;
  nickname: string;
  username: string | null;
  email: string;
};

export type Partnership = {
  id: string;
  bot_id: string;
  status: "PENDING" | "ACTIVE" | "PAUSED" | "DECLINED" | "REVOKED";
  partner_percent: number;
  bot_fee: number;
  accepted_at: string | null;
  created_at: string;
  owner: PartnerUser | null;
  partner: PartnerUser | null;
  bot?: { id: string; name: string; username: string };
  can_edit?: boolean;
  notify_webhook_url?: string | null;
  flows?: { id: string; name: string }[];
};

export type CommissionStatus = "pending" | "paid" | "denied";

export type FinanceSale = {
  id: string;
  order_id: string;
  paid_at: string;
  gross: number;
  gateway_fee: number;
  bot_fee: number;
  net: number;
  partner_percent: number;
  partner_amount: number;
  owner_amount: number;
  payout_status: CommissionStatus;
  status_note: string | null;
  status_changed_at: string | null;
};

export type FinancePayout = {
  id: string;
  party: "owner" | "partner";
  amount: number;
  note: string | null;
  paid_at: string;
};

export type FinancePanel = {
  has_partner: boolean;
  as_owner?: boolean;
  partnership_id?: string;
  status?: string;
  partner?: PartnerUser | null;
  owner?: PartnerUser | null;
  partner_percent?: number;
  bot_fee?: number;
  period_label?: string;
  totals?: {
    sales: number;
    gross: number;
    gateway_fee: number;
    bot_fee: number;
    net: number;
    partner_amount: number;
    owner_amount: number;
    partner_withdrawn: number;
    owner_withdrawn: number;
    partner_balance: number;
    owner_balance: number;
  };
  by_status?: Record<CommissionStatus, { count: number; partner_amount: number }>;
  sales?: FinanceSale[];
  payouts?: FinancePayout[];
};

// ---------------- owner side

export function botPartners(botId: string) {
  return apiRequest<{
    bot: { id: string; name: string; username: string };
    partners: Partnership[];
    default_bot_fee: number;
    can_zero_fee: boolean;
    has_active: boolean;
    active_percent: number;
    active_percent_remaining: number;
  }>(`/api/bot-partners/bots/${botId}`);
}

export function invitePartner(botId: string, body: { identifier: string; partner_percent: string; bot_fee?: string }) {
  return apiRequest<Partnership>(`/api/bot-partners/bots/${botId}/invite`, { method: "POST", body });
}

export function updatePartnership(
  id: string,
  body: { partner_percent?: string; bot_fee?: string; status?: "ACTIVE" | "PAUSED" | "REVOKED" },
) {
  return apiRequest<Partnership>(`/api/bot-partners/${id}`, { method: "PATCH", body });
}

export function removePartnership(id: string) {
  return apiRequest<void>(`/api/bot-partners/${id}`, { method: "DELETE" });
}

export function ownerFinance(botId: string, period: MetricsPeriod, partnershipId?: string) {
  const params = new URLSearchParams(periodParams(period));
  if (partnershipId) params.set("partnership_id", partnershipId);
  return apiRequest<FinancePanel>(`/api/bot-partners/bots/${botId}/finance?${params}`);
}

export function addPayout(id: string, body: { party: "owner" | "partner"; amount: string; note?: string; paid_at?: string }) {
  return apiRequest<FinancePayout>(`/api/bot-partners/${id}/payouts`, { method: "POST", body });
}

export function setCommissionStatus(saleId: string, body: { status: CommissionStatus; note?: string }) {
  return apiRequest<{ id: string; payout_status: CommissionStatus; status_note: string | null; status_changed_at: string | null }>(
    `/api/bot-partners/sales/${saleId}/status`,
    { method: "PATCH", body },
  );
}

// ---------------- partner side

export function mySharedBots() {
  return apiRequest<{ shared: Partnership[] }>(`/api/bot-partners/shared`);
}

export function acceptInvite(id: string) {
  return apiRequest<Partnership>(`/api/bot-partners/${id}/accept`, { method: "POST" });
}

export function declineInvite(id: string) {
  return apiRequest<{ ok: boolean }>(`/api/bot-partners/${id}/decline`, { method: "POST" });
}

export function sharedBotDetail(botId: string) {
  return apiRequest<Partnership>(`/api/bot-partners/shared/${botId}`);
}

export function partnerFinance(botId: string, period: MetricsPeriod) {
  return apiRequest<FinancePanel>(`/api/bot-partners/shared/${botId}/finance?${new URLSearchParams(periodParams(period))}`);
}

export function setPartnerWebhook(botId: string, notifyWebhookUrl: string | null) {
  return apiRequest<{ notify_webhook_url: string | null }>(`/api/bot-partners/shared/${botId}/notify`, {
    method: "PATCH",
    body: { notify_webhook_url: notifyWebhookUrl },
  });
}

export const brl = (value: number | null | undefined) =>
  (value ?? 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
