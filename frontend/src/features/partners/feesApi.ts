import { apiRequest } from "@/services/api";
import type { FeeChangeLog, UserFeeInfo, PartnerFeeInfo } from "@/types/permissions";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

interface FeeUpdateRequest {
  user_id?: string;
  new_fee: number | null;
  reason?: string;
}

interface CurrentFeesResponse {
  partners: PartnerFeeInfo[];
  users_with_custom_fees: UserFeeInfo[];
}

export function useCurrentFees() {
  return useQuery({
    queryKey: ["admin", "fees", "current"],
    queryFn: () => apiRequest<CurrentFeesResponse>("/api/admin/fees/current"),
    staleTime: 30_000,
  });
}

export function useUserFee(userId: string | null) {
  return useQuery({
    queryKey: ["admin", "fees", "user", userId],
    queryFn: () => apiRequest<UserFeeInfo>(`/api/admin/fees/user/${userId}`),
    enabled: !!userId,
    staleTime: 30_000,
  });
}

export function useUpdateUserFee() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: FeeUpdateRequest) => {
      return apiRequest<{ success: boolean; user_id: string; old_fee: number | null; new_fee: number | null; message: string }>(
        "/api/admin/fees/user",
        {
          method: "PUT",
          body: data,
        }
      );
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin", "fees"] });
    },
  });
}

export function useUpdateGlobalFee() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: Omit<FeeUpdateRequest, "user_id">) => {
      return apiRequest<{ success: boolean; affected_users: number; new_fee: number | null; message: string }>(
        "/api/admin/fees/global",
        {
          method: "PUT",
          body: data,
        }
      );
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin", "fees"] });
    },
  });
}

export function useFeeHistory(userId?: string) {
  return useQuery({
    queryKey: ["admin", "fees", "history", userId],
    queryFn: () => {
      const params = userId ? `?user_id=${userId}` : "";
      return apiRequest<{ history: FeeChangeLog[]; count: number }>(`/api/admin/fees/history${params}`);
    },
    staleTime: 30_000,
  });
}

export function usePreviewGlobalFeeChange() {
  return useMutation({
    mutationFn: (newFee: number | null) => {
      return apiRequest<{
        affected_count: number;
        affected_users: Array<{ user_id: string; name: string; email: string; current_fee: number | null; new_fee: number | null }>;
        total_users: number;
        new_fee: number | null;
      }>("/api/admin/fees/preview-global", {
        method: "POST",
        body: { new_fee: newFee },
      });
    },
  });
}

export const brlFee = (value: number | null) => {
  if (value === null) return "Padrão da plataforma";
  return `R$ ${value.toFixed(2).replace(".", ",")}`;
};
