import { apiRequest } from "@/services/api";
import type { UserPermissions, PartnerPermissions, PlatformType } from "@/types/permissions";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

export function usePartnerPermissions(userId: string | null) {
  return useQuery({
    queryKey: ["admin", "partner-permissions", userId],
    queryFn: () => apiRequest<UserPermissions>(`/api/admin/partner-permissions/${userId}`),
    enabled: !!userId,
    staleTime: 30_000,
  });
}

export function useUpdatePartnerPermissions() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      userId,
      platform,
      permissions,
    }: {
      userId: string;
      platform: PlatformType;
      permissions: Partial<PartnerPermissions>;
    }) => {
      return apiRequest<{ success: boolean; platform: string; permissions: PartnerPermissions }>(
        "/api/admin/partner-permissions",
        {
          method: "PUT",
          body: {
            user_id: userId,
            platform,
            permissions,
          },
        }
      );
    },
    onSuccess: (_, variables) => {
      void queryClient.invalidateQueries({
        queryKey: ["admin", "partner-permissions", variables.userId],
      });
    },
  });
}

export function useInitializePartnerPermissions() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (userId: string) => {
      return apiRequest<UserPermissions>(`/api/admin/partner-permissions/initialize/${userId}`, {
        method: "POST",
      });
    },
    onSuccess: (_, userId) => {
      void queryClient.invalidateQueries({
        queryKey: ["admin", "partner-permissions", userId],
      });
    },
  });
}
