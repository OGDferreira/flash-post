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
  flows: { id: string; name: string; plans: number; upsells: number; downsells: number; in_use: boolean }[];
};

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

export function usePartnerMe(params: Record<string, string> = {}) {
  return useQuery({
    queryKey: ["partners", "me", params],
    queryFn: () => apiRequest<PartnerMe>(`/api/partners/me?${new URLSearchParams(params)}`),
    staleTime: 30_000,
  });
}

export function useAcceptCommission() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (percent: number) => apiRequest("/api/partners/me/accept", { method: "POST", body: { percent: String(percent) } }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["partners"] }),
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
    mutationFn: (id: string) => apiRequest<{ id: string; name: string }>(`/api/partners/shared/${kind}/${id}/use`, { method: "POST" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["partners"] });
      void queryClient.invalidateQueries({ queryKey: kind === "flows" ? ["bots", "flows"] : ["loops"] });
    },
  });
}

export function useShareToggle(kind: "loops" | "flows") {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, shared }: { id: string; shared: boolean }) =>
      apiRequest(`/api/partners/${kind}/${id}/share`, { method: "POST", body: { shared } }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: kind === "flows" ? ["bots", "flows"] : ["loops"] }),
  });
}

export function useNotices() {
  return useQuery({
    queryKey: ["partners", "notifications"],
    queryFn: () => apiRequest<{ items: Notice[]; unread: number }>("/api/partners/notifications"),
    staleTime: 60_000,
  });
}

export function useMarkNoticesRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiRequest("/api/partners/notifications/read", { method: "POST" }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["partners", "notifications"] }),
  });
}
