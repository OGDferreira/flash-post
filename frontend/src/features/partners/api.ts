import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiRequest } from "@/services/api";

export type Role = "super_admin" | "partner" | "chief" | "independent";

export type SaleTotals = { sales: number; gross: number; fees: number; commission: number; net: number };

export type Sale = {
  id: string;
  offer_name: string;
  paid_at: string | null;
  gross: number;
  fee: number;
  percent: number | null;
  commission: number;
  net: number;
};

export type PartnerMe = {
  role: Role;
  period_label: string;
  basis: string;
  shop_ref: string | null;
  partnership: null | {
    chief_name: string;
    chief_nickname: string;
    proposed_percent: number;
    accepted_percent: number | null;
    accepted_at: string | null;
    pending_acceptance: boolean;
    since: string;
  };
  totals: SaleTotals | null;
  sales: Sale[];
  permissions?: {
    flashpost: {
      can_view_dashboard: boolean;
      can_view_ranking: boolean;
      can_view_accounts: boolean;
      can_view_meta_apps: boolean;
      can_view_settings: boolean;
      can_view_contact: boolean;
    };
    flashbot: {
      can_view_bot_dashboard: boolean;
      can_view_leads: boolean;
      can_view_wallets: boolean;
    };
  };
};

export type SharedTemplates = {
  available: boolean;
  accepted: boolean;
  loops: {
    id: string;
    name: string;
    post_type: string;
    interval_min_minutes: number;
    interval_max_minutes: number;
    daily_limit_per_account: number;
    media_count: number;
    in_use: boolean;
  }[];
  flows: {
    id: string;
    name: string;
    in_use: boolean;
    loop_id: string | null;
    loop_name: string | null;
    loop_in_use: boolean;
    /** The owner's rules for this partner: read-only for the seller. */
    rules: SellerRules;
  }[];
};

export type GatewayId = "smokepay" | "snakepay";

export type SellerRules = {
  set_by_owner: boolean;
  gateway: GatewayId;
  /** SnakePay funnel the seller must configure their own SnakePay for before using. */
  needs_setup: boolean;
};

/** One funnel of mine shared with one partner ("Que compartilhei"). ``rule: "partnership"``
 *  = shared before the per-partner rules: it follows the partnership percentage until saved. */
export type FlowShare = {
  id: string | null;
  flow_id: string;
  flow_name: string;
  partner_id: string;
  partner_name: string | null;
  gateway: GatewayId;
  seller_percent: number;
  owner_percent: number;
  seller_shop_id: string | null;
  owner_shop_id: string | null;
  /** The owner keeps 100% of this partner's sales; the partner is never told. */
  owner_takes_all?: boolean;
  loop_id: string | null;
  status: "ACTIVE" | "REVOKED";
  rule: "share" | "partnership";
  updated_at: string | null;
  stats: { sales: number; gross: number; commission: number } | null;
};

export type FlowShareInput = {
  flow_id: string;
  partner_id: string;
  gateway: GatewayId;
  seller_percent: string;
  owner_percent: string;
  /** undefined keeps the saved ShopID. */
  seller_shop_id?: string;
  owner_shop_id?: string;
  /** undefined keeps the paired loop; null removes it. */
  loop_id?: string | null;
  owner_takes_all?: boolean;
};

export type ShareHistoryItem = { action: string; details: Record<string, unknown>; created_at: string | null };

export type Operations = {
  period_label: string;
  loops: { id: string; name: string; status: string; accounts: number; posts: number; from_template: boolean }[];
  bots: {
    id: string;
    name: string;
    username: string;
    status: string;
    is_active: boolean;
    flow_name: string | null;
    leads: number;
    sales: number;
    revenue: number;
  }[];
  flows: { id: string; name: string; from_template: boolean; customized_at: string | null; shared: boolean }[];
  totals: SaleTotals | null;
  commission?: SaleTotals;
  sales: Sale[];
};

export type Notice = { id: string; kind: string; title: string; body: string; url: string | null; read: boolean; created_at: string };

export const brl = (value: number | null | undefined) =>
  (value ?? 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

export function usePartnerMe(params: Record<string, string> = {}, enabled = true) {
  return useQuery({
    queryKey: ["partners", "me", params],
    queryFn: () => apiRequest<PartnerMe>(`/api/partners/me?${new URLSearchParams(params)}`),
    enabled,
    staleTime: 30_000,
  });
}

export function useSharedTemplates(enabled = true) {
  return useQuery({
    queryKey: ["partners", "shared"],
    queryFn: () => apiRequest<SharedTemplates>("/api/partners/shared"),
    enabled,
    staleTime: 30_000,
  });
}

export function useUseTemplate(kind: "loops" | "flows") {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiRequest<{ id: string; name: string; loop?: { id: string; name: string } | null }>(`/api/partners/shared/${kind}/${id}/use`, { method: "POST" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["partners"] });
      void queryClient.invalidateQueries({ queryKey: kind === "flows" ? ["bots", "flows"] : ["loops"] });
    },
  });
}

export type ShareInput = {
  id: string;
  shared: boolean;
  /** null = every partner. */
  partner_ids?: string[] | null;
  /** Funnels only: the loop that goes out together (optional). */
  loop_id?: string | null;
};

export function useShareToggle(kind: "loops" | "flows") {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, shared, partner_ids = null, loop_id = null }: ShareInput) =>
      apiRequest(`/api/partners/${kind}/${id}/share`, { method: "POST", body: { shared, partner_ids, loop_id } }),
    onSuccess: () => {
      // sharing a funnel can share its loop too
      void queryClient.invalidateQueries({ queryKey: ["bots", "flows"] });
      void queryClient.invalidateQueries({ queryKey: ["loops"] });
    },
  });
}

export type PartnerOption = { id: string; name: string; nickname: string };

export function useFlowShares(enabled = true) {
  return useQuery({
    queryKey: ["partners", "flow-shares"],
    queryFn: () => apiRequest<{ basis: string; items: FlowShare[] }>("/api/partners/flow-shares"),
    enabled,
  });
}

function useShareInvalidation() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: ["partners"] });
    void queryClient.invalidateQueries({ queryKey: ["bots", "flows"] });
    void queryClient.invalidateQueries({ queryKey: ["loops"] });
  };
}

export function useSaveFlowShare() {
  const invalidate = useShareInvalidation();
  return useMutation({
    mutationFn: (input: FlowShareInput) => apiRequest<FlowShare>("/api/partners/flow-shares", { method: "PUT", body: input }),
    onSuccess: invalidate,
  });
}

export function useRevokeFlowShare() {
  const invalidate = useShareInvalidation();
  return useMutation({
    mutationFn: (id: string) => apiRequest<FlowShare>(`/api/partners/flow-shares/${id}`, { method: "DELETE" }),
    onSuccess: invalidate,
  });
}

export function useShareHistory(id: string | null) {
  return useQuery({
    queryKey: ["partners", "flow-shares", id, "history"],
    queryFn: () => apiRequest<{ items: ShareHistoryItem[] }>(`/api/partners/flow-shares/${id}/history`),
    enabled: id !== null,
  });
}

/** Chief: their active partners, to pick who receives a funnel or a loop. */
export function useMyPartners(enabled = true) {
  return useQuery({
    queryKey: ["partners", "mine"],
    queryFn: () => apiRequest<{ partners: PartnerOption[] }>("/api/partners/mine"),
    enabled,
    staleTime: 60_000,
  });
}

export function useNotices(enabled = true) {
  return useQuery({
    queryKey: ["partners", "notifications"],
    queryFn: () => apiRequest<{ items: Notice[]; unread: number }>("/api/partners/notifications"),
    enabled,
    staleTime: 30_000,
    refetchInterval: 20_000,
  });
}

export function useMarkNoticesRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiRequest("/api/partners/notifications/read", { method: "POST" }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["partners", "notifications"] }),
  });
}

/** How a partner sees the operation owner: "Guilherme Sócio" (falls back to "seu sócio"). */
export function useChiefLabel() {
  const me = usePartnerMe();
  const link = me.data?.partnership;
  const first = (link?.chief_name || link?.chief_nickname || "").trim().split(/\s+/)[0];
  return first ? `${first} Sócio` : "seu sócio";
}
