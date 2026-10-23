import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiRequest } from "@/services/api";

export type GatewayBalance = {
  gateway: "smokepay" | "snakepay";
  available: number;
  withdrawable: number;
  fee: number | null;
  ready: boolean; // SnakePay: the account's key and Cash Out secret are saved
  estimated: boolean;
  min: number;
};

export type Withdrawal = {
  id: string;
  gateway?: "smokepay" | "snakepay";
  amount: number;
  status: "PAID" | "REQUESTED" | "REJECTED" | "PROCESSING" | "FAILED";
  fee?: number | null;
  note: string | null;
  pix_key_type: string | null;
  pix_key: string | null;
  e2e_id?: string | null;
  owner: string | null;
  created_at: string | null;
  processed_at: string | null;
  shop_ref?: string;
  owner_available?: number | null;
};

export type Goal = {
  target: number;
  percent: number;
  prize: string;
  reached: number[];
  goals: GoalItem[];
};

export type GoalItem = { amount: number; prize: string; reached: boolean; current?: boolean; image_url?: string | null };

export type Wallet = {
  is_main_account: boolean;
  /** Partners only see billing, net balance and what was paid out; the Super Admin withdraws. */
  is_partner?: boolean;
  shop_ref: string | null;
  balance_source: "smokepay" | "estimate";
  month_revenue: number;
  month_shark_revenue?: number;
  snakepay_received?: number; // everything SnakePay sent to the user's own account
  snakepay_sales?: number;
  snakepay_commissions?: number;
  snakepay_fees?: number; // Super Admin: platform and per-sale fees kept in the charging account
  month_flash_revenue?: number;
  month_commissions?: number;
  gateways?: GatewayBalance[];
  withdrawals_blocked?: boolean;
  /** Super Admin only: the per-sale Falcon Bot fee collected (month and today). */
  falcon_fees_month?: number;
  falcon_fees_month_count?: number;
  falcon_fees_today?: number;
  falcon_fees_today_count?: number;
  goal: Goal;
  earned: number;
  commissions_received: number;
  commission_paid?: number;
  withdrawn: number;
  pending: number;
  available: number;
  withdrawable?: number;
  withdraw_fee?: number;
  min_withdrawal: number;
  withdrawals: Withdrawal[];
};

export const brl = (value: number) => value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
export const compact = (value: number) =>
  value >= 1_000_000 ? `${value / 1_000_000}M` : value >= 1000 ? `${value / 1000}k` : String(value);

/** Award title: the revenue needed, e.g. "R$ 10 mil", "R$ 1 milhão", "R$ 5 milhões". */
export const awardTitle = (amount: number) =>
  amount >= 1_000_000
    ? `R$ ${(amount / 1_000_000).toLocaleString("pt-BR")} ${amount === 1_000_000 ? "milhão" : "milhões"}`
    : `R$ ${(amount / 1000).toLocaleString("pt-BR")} mil`;

/** An award only unlocks once its revenue goal is reached; the next goal stays locked too. */
export const awardUnlocked = (goal: Pick<GoalItem, "reached">) => goal.reached;

export function useWalletSummary(enabled: boolean) {
  return useQuery({
    queryKey: ["wallet", "summary"],
    queryFn: () =>
      apiRequest<{ available: boolean; month_revenue?: number; target?: number; percent?: number; prize?: string }>("/api/wallet/summary"),
    enabled,
    staleTime: 60_000,
    refetchInterval: 120_000,
  });
}

export function useWallet() {
  return useQuery({
    queryKey: ["wallet", "full"],
    queryFn: () => apiRequest<Wallet>("/api/wallet"),
    staleTime: 15_000,
    // While a withdrawal is on its way, check every 5 s so it flips to "Pago" by itself.
    refetchInterval: (query) => (query.state.data?.withdrawals.some((item) => item.status === "PROCESSING") ? 5_000 : false),
  });
}

export function useWalletMutations() {
  const queryClient = useQueryClient();
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ["wallet"] });
  return {
    request: useMutation({
      mutationFn: (body: { amount?: string; gateway?: string; withdraw_all?: boolean; pix_key_type?: string; pix_key?: string; note?: string }) =>
        apiRequest<Withdrawal>("/api/wallet/withdrawals", { method: "POST", body }),
      onSuccess: refresh,
    }),
  };
}

export function useGoals(enabled = true) {
  return useQuery({
    queryKey: ["wallet", "goals"],
    queryFn: () => apiRequest<({ available: true; month_revenue: number } & Goal) | { available: false }>("/api/wallet/goals"),
    enabled,
    staleTime: 60_000,
  });
}

export type AwardItem = { amount: number; prize: string; image_url: string | null; custom: boolean };

export function useAwards() {
  const queryClient = useQueryClient();
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ["admin", "awards"] }).then(() => queryClient.invalidateQueries({ queryKey: ["wallet"] }));
  return {
    list: useQuery({ queryKey: ["admin", "awards"], queryFn: () => apiRequest<{ items: AwardItem[] }>("/api/admin/awards") }),
    upload: useMutation({
      mutationFn: ({ amount, file }: { amount: number; file: File }) =>
        apiRequest(`/api/admin/awards/${amount}/image`, { method: "PUT", body: file }),
      onSuccess: refresh,
    }),
    remove: useMutation({
      mutationFn: (amount: number) => apiRequest(`/api/admin/awards/${amount}/image`, { method: "DELETE" }),
      onSuccess: refresh,
    }),
  };
}

export type PartnerWallet = {
  user_id: string;
  gateways?: GatewayBalance[];
  withdrawals_blocked?: boolean;
  name: string;
  email: string;
  chief: string | null;
  shop_ref: string;
  month_revenue: number;
  earned: number;
  available: number;
  withdrawable: number;
  withdraw_fee: number;
  withdrawn: number;
  pending: number;
  balance_source: "smokepay" | "estimate";
  withdrawals: Withdrawal[];
};

/** Super Admin: every partner's balance, payouts and withdrawal history. */
export function usePartnerWallets() {
  const queryClient = useQueryClient();
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ["admin", "partner-wallets"] });
  return {
    list: useQuery({
      queryKey: ["admin", "partner-wallets"],
      queryFn: () => apiRequest<{ items: PartnerWallet[]; min_withdrawal: number; withdrawals_blocked?: boolean }>("/api/admin/partner-wallets"),
      staleTime: 15_000,
      refetchInterval: (query) =>
        query.state.data?.items.some((item) => item.withdrawals.some((w) => w.status === "PROCESSING")) ? 5_000 : false,
    }),
    withdraw: useMutation({
      mutationFn: ({ userId, ...body }: { userId: string; amount?: string; gateway?: string; withdraw_all?: boolean; pix_key_type: string; pix_key: string; note?: string }) =>
        apiRequest<Withdrawal>(`/api/admin/partner-wallets/${userId}/withdrawals`, { method: "POST", body }),
      onSuccess: refresh,
    }),
  };
}
