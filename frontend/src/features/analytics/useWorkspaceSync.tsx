import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, RefreshCw, TriangleAlert } from "lucide-react";

import { formatDateTime } from "@/features/analytics/period";
import { apiRequest } from "@/services/api";

export type SyncStatus = {
  running: boolean;
  total: number;
  done: number;
  failed: number;
  started_at: string | null;
  finished_at: string | null;
};

const KEY = ["analytics", "sync-status"] as const;

/** Shared, polling view of the workspace's background Meta sync. */
export function useSyncStatus() {
  return useQuery({
    queryKey: KEY,
    queryFn: () => apiRequest<SyncStatus>("/api/analytics/sync-status"),
    refetchInterval: (query) => (query.state.data?.running ? 3000 : false),
    staleTime: 0,
  });
}

/**
 * Starts the background sync once when the Analytics page opens (the server
 * skips it if one ran recently) and refreshes the metrics when it finishes.
 */
export function useWorkspaceSync() {
  const queryClient = useQueryClient();
  const status = useSyncStatus();
  const start = useMutation({
    mutationFn: (force: boolean) =>
      apiRequest<SyncStatus>(`/api/analytics/sync${force ? "?force=true" : ""}`, { method: "POST" }),
    onSuccess: (data) => queryClient.setQueryData(KEY, data),
  });
  const started = useRef(false);
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    start.mutate(false);
  }, [start]);

  const wasRunning = useRef(false);
  const running = Boolean(status.data?.running);
  useEffect(() => {
    if (wasRunning.current && !running) {
      void queryClient.invalidateQueries({
        predicate: (query) => query.queryKey[0] === "analytics" && query.queryKey[1] !== "sync-status",
      });
      void queryClient.invalidateQueries({ queryKey: ["instagram", "accounts"] });
    }
    wasRunning.current = running;
  }, [running, queryClient]);

  return { status, start };
}

export function SyncStatusBar({
  status,
  starting,
  onRefresh,
}: {
  status: SyncStatus | undefined;
  starting: boolean;
  onRefresh: () => void;
}) {
  const running = Boolean(status?.running) || starting;
  return (
    <div
      aria-live="polite"
      className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-line-soft bg-surface-inset px-3 py-2 text-xs text-[#94a3b8]"
    >
      <span className="flex items-center gap-2">
        {running ? (
          <>
            <RefreshCw className="animate-spin text-[#8295ff]" size={13} />
            Atualizando dados da Meta em segundo plano
            {status && status.total > 0 ? ` (${status.done}/${status.total} contas)` : "…"} — você pode continuar navegando.
          </>
        ) : status?.finished_at ? (
          <>
            {status.failed > 0 ? (
              <TriangleAlert className="text-[#f2d48a]" size={13} />
            ) : (
              <CheckCircle2 className="text-[#7ee2bd]" size={13} />
            )}
            Última atualização: {formatDateTime(status.finished_at)}
            {status.failed > 0 ? ` · ${status.failed} conta(s) com falha na Meta` : ""}
          </>
        ) : (
          "Dados da Meta ainda não atualizados."
        )}
      </span>
      <button className="btn-ghost !min-h-8 !px-2.5 text-xs" disabled={running} onClick={onRefresh} type="button">
        <RefreshCw size={13} /> Atualizar agora
      </button>
    </div>
  );
}
