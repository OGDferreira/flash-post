import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowUpRight, CircleAlert, LoaderCircle, Smartphone } from "lucide-react";
import { Link } from "react-router-dom";

import { Modal } from "@/components/ui/Modal";
import { apiRequest } from "@/services/api";

export type InstagramMetaApp = {
  id: string;
  display_name: string;
  app_id: string;
  is_selected: boolean;
  connected_accounts: number;
};

export type InstagramMetaAppsResponse = {
  selected_app_id: string | null;
  can_manage: boolean;
  apps: InstagramMetaApp[];
};

export const metaAppsQueryKey = ["instagram", "apps"] as const;

type ConnectAccountModalProps = {
  open: boolean;
  onClose: () => void;
  /** Where the OAuth callback should send the user back to. */
  returnTo: "/dashboard" | "/feature/accounts";
};

function connectedLabel(count: number) {
  if (count === 0) return "Sem contas conectadas";
  return count === 1 ? "1 conta conectada" : `${count} contas conectadas`;
}

/**
 * Meta app picker shared by the owner and collaborator flows. The backend
 * re-checks membership, role and workspace for both the start and the OAuth
 * callback, so the modal only chooses which app the new account will use.
 */
export function ConnectAccountModal({ open, onClose, returnTo }: ConnectAccountModalProps) {
  const [pendingAppId, setPendingAppId] = useState<string | null>(null);
  const apps = useQuery({
    queryKey: metaAppsQueryKey,
    queryFn: () => apiRequest<InstagramMetaAppsResponse>("/api/instagram/apps"),
    enabled: open,
    staleTime: 30_000,
    retry: false,
  });
  const connect = useMutation({
    mutationFn: (appId: string) =>
      apiRequest<{ authorization_url: string }>(
        `/api/instagram/connect?${new URLSearchParams({ app_id: appId, return_to: returnTo })}`,
        { method: "POST" },
      ),
    onMutate: (appId) => setPendingAppId(appId),
    onSuccess: ({ authorization_url }) => window.location.assign(authorization_url),
    onError: () => setPendingAppId(null),
  });
  const appList = apps.data?.apps ?? [];

  return (
    <Modal
      busy={connect.isPending}
      description="A nova conta será vinculada ao aplicativo escolhido. As contas já conectadas não mudam."
      onClose={onClose}
      open={open}
      title="Conectar conta do Instagram"
    >
      {apps.isLoading && (
        <div className="space-y-2.5" aria-busy="true" aria-label="Carregando aplicativos">
          {[0, 1].map((item) => (
            <div className="skeleton h-[72px]" key={item} />
          ))}
        </div>
      )}

      {apps.error && (
        <div className="flex items-start gap-3 rounded-xl border border-[#47252d] bg-[#1a1013]/80 p-4 text-sm text-[#f1a3ad]">
          <CircleAlert className="mt-0.5 shrink-0" size={16} />
          <div>
            <p>Não foi possível carregar os aplicativos Meta.</p>
            <button className="mt-2 text-xs font-medium underline" onClick={() => void apps.refetch()} type="button">
              Tentar novamente
            </button>
          </div>
        </div>
      )}

      {apps.data && appList.length === 0 && (
        <div className="rounded-xl border border-dashed border-line px-4 py-5 text-center">
          <Smartphone className="mx-auto text-[#7186ff]" size={22} />
          <p className="mt-3 text-sm text-[#cbd5e1]">Nenhum aplicativo Meta configurado.</p>
          {apps.data.can_manage ? (
            <Link className="btn-secondary mt-4" onClick={onClose} to="/feature/meta-apps">
              Configurar aplicativo Meta
            </Link>
          ) : (
            <p className="mt-1 text-xs text-[#94a3b8]">Peça ao responsável do workspace para configurar.</p>
          )}
        </div>
      )}

      {appList.length > 0 && (
        <ul className="space-y-2.5">
          {appList.map((app) => {
            const isPending = pendingAppId === app.id && connect.isPending;
            const empty = app.connected_accounts === 0;
            return (
              <li key={app.id}>
                <button
                  className="group flex w-full items-center gap-3 rounded-2xl border border-line bg-surface-inset p-4 text-left transition hover:border-[#536dfe]/60 hover:bg-[#536dfe]/[0.07] disabled:cursor-wait disabled:opacity-60"
                  disabled={connect.isPending}
                  onClick={() => connect.mutate(app.id)}
                  type="button"
                >
                  <span className="grid size-10 shrink-0 place-items-center rounded-xl border border-[#33447c] bg-[#11182d] text-sm font-semibold text-[#9baaff]">
                    {app.display_name.slice(0, 1).toUpperCase()}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex flex-wrap items-center gap-2">
                      <span className="truncate font-medium text-[#f5f7fb]">{app.display_name}</span>
                      {app.is_selected && (
                        <span className="rounded-full bg-[#536dfe]/15 px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.08em] text-[#aab7ff]">
                          Padrão
                        </span>
                      )}
                    </span>
                    <span className="mt-1 block truncate text-xs text-[#64748b]">App ID {app.app_id}</span>
                    <span
                      className={`mt-2 inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium ${
                        empty
                          ? "bg-[#f2d48a]/10 text-[#f2d48a]"
                          : "bg-[#2dd4a0]/10 text-[#7ee2bd]"
                      }`}
                    >
                      <span className={`size-1.5 rounded-full ${empty ? "bg-[#f2d48a]" : "bg-[#2dd4a0]"}`} />
                      {connectedLabel(app.connected_accounts)}
                    </span>
                  </span>
                  {isPending ? (
                    <LoaderCircle className="shrink-0 animate-spin text-[#aab7ff]" size={18} />
                  ) : (
                    <ArrowUpRight
                      className="shrink-0 text-[#64748b] transition group-hover:text-[#aab7ff]"
                      size={18}
                    />
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      )}

      {connect.error && (
        <p className="mt-3 rounded-xl border border-[#47252d] bg-[#1a1013]/80 px-4 py-3 text-sm text-[#f1a3ad]" role="alert">
          Não foi possível iniciar a conexão. Tente novamente.
        </p>
      )}
    </Modal>
  );
}
