import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiRequest } from "@/services/api";

export type Withdrawal = {
  id: string;
  amount: number;
  status: "PAID" | "REQUESTED" | "REJECTED" | "PROCESSING" | "FAILED";
  fee?: number | null;
  note: string | null;
  pix_key_type: string | null;
  pix_key: string | null;
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
  shop_ref: string | null;
  balance_source: "smokepay" | "estimate";
  month_revenue: number;
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
  return useQuery({ queryKey: ["wallet", "full"], queryFn: () => apiRequest<Wallet>("/api/wallet"), staleTime: 15_000 });
}

export function useWalletMutations() {
  const queryClient = useQueryClient();
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ["wallet"] });
  return {
    request: useMutation({
      mutationFn: (body: { amount: string; pix_key_type?: string; pix_key?: string; note?: string }) =>
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

export type AwardItem = { amount: number; prize: string; image_url: string | null };

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
