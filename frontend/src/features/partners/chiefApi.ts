import { apiRequest } from "@/services/api";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ChiefPartner, PartnerFolder, PartnerAccount, PartnerLoop, LoopAccount } from "@/types/chief";

export function useChiefPartners() {
  return useQuery({
    queryKey: ["chief", "partners"],
    queryFn: () => apiRequest<{ partners: ChiefPartner[]; count: number }>("/api/chief/partners"),
    staleTime: 30_000,
  });
}

export function usePartnerFolders(workspaceId: string | null) {
  return useQuery({
    queryKey: ["chief", "partners", workspaceId, "folders"],
    queryFn: () => apiRequest<{ folders: PartnerFolder[] }>(`/api/chief/partners/${workspaceId}/folders`),
    enabled: !!workspaceId,
    staleTime: 30_000,
  });
}

export function usePartnerAccounts(workspaceId: string | null, folderId?: string | null) {
  return useQuery({
    queryKey: ["chief", "partners", workspaceId, "accounts", folderId],
    queryFn: () => {
      const params = folderId ? `?folder_id=${folderId}` : "";
      return apiRequest<{ accounts: PartnerAccount[] }>(`/api/chief/partners/${workspaceId}/accounts${params}`);
    },
    enabled: !!workspaceId,
    staleTime: 30_000,
  });
}

export function usePartnerLoops(workspaceId: string | null) {
  return useQuery({
    queryKey: ["chief", "partners", workspaceId, "loops"],
    queryFn: () => apiRequest<{ loops: PartnerLoop[] }>(`/api/chief/partners/${workspaceId}/loops`),
    enabled: !!workspaceId,
    staleTime: 30_000,
  });
}

export function useLoopAccounts(workspaceId: string | null, loopId: string | null) {
  return useQuery({
    queryKey: ["chief", "partners", workspaceId, "loops", loopId, "accounts"],
    queryFn: () => apiRequest<{ loop_id: string; accounts: LoopAccount[] }>(
      `/api/chief/partners/${workspaceId}/loops/${loopId}/accounts`
    ),
    enabled: !!workspaceId && !!loopId,
    staleTime: 30_000,
  });
}

export function useCreatePartnerFolder() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ workspaceId, data }: { workspaceId: string; data: { name: string; color?: string; auto_prefixes?: string[]; auto_enabled?: boolean } }) => {
      return apiRequest<{ success: boolean; folder: PartnerFolder }>(
        `/api/chief/partners/${workspaceId}/folders`,
        { method: "POST", body: data }
      );
    },
    onSuccess: (_, variables) => {
      void queryClient.invalidateQueries({ queryKey: ["chief", "partners", variables.workspaceId] });
    },
  });
}

export function useAssignAccountToFolder() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ workspaceId, accountId, folderId }: { workspaceId: string; accountId: string; folderId: string | null }) => {
      return apiRequest<{ success: boolean; account_id: string; folder_id: string | null }>(
        `/api/chief/partners/${workspaceId}/accounts/assign-folder`,
        { method: "PUT", body: { account_id: accountId, folder_id: folderId } }
      );
    },
    onSuccess: (_, variables) => {
      void queryClient.invalidateQueries({ queryKey: ["chief", "partners", variables.workspaceId] });
    },
  });
}

export function useAddAccountToLoop() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ workspaceId, loopId, accountId }: { workspaceId: string; loopId: string; accountId: string }) => {
      return apiRequest<{ success: boolean; loop_account_id: string }>(
        `/api/chief/partners/${workspaceId}/loops/${loopId}/accounts`,
        { method: "POST", body: { account_id: accountId } }
      );
    },
    onSuccess: (_, variables) => {
      void queryClient.invalidateQueries({ queryKey: ["chief", "partners", variables.workspaceId, "loops", variables.loopId] });
    },
  });
}

export function useRemoveAccountFromLoop() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ workspaceId, loopId, accountId }: { workspaceId: string; loopId: string; accountId: string }) => {
      return apiRequest<{ success: boolean; removed: boolean }>(
        `/api/chief/partners/${workspaceId}/loops/${loopId}/accounts/${accountId}`,
        { method: "DELETE" }
      );
    },
    onSuccess: (_, variables) => {
      void queryClient.invalidateQueries({ queryKey: ["chief", "partners", variables.workspaceId, "loops", variables.loopId] });
    },
  });
}
