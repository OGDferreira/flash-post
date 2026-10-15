import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowUpRight, CircleAlert, LoaderCircle, Smartphone, X } from "lucide-react";
import { Link } from "react-router-dom";

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

type ConnectAppsPanelProps = {
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
export function ConnectAppsPanel({ onClose, returnTo }: ConnectAppsPanelProps) {
  const [pendingAppId, setPendingAppId] = useState<string | null>(null);
  const apps = useQuery({
    queryKey: metaAppsQueryKey,
    queryFn: () => apiRequest<InstagramMetaAppsResponse>("/api/instagram/apps"),
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
    <section aria-label="Conectar conta do Instagram" className="glass-panel p-4 sm:p-5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-fg">Escolha o aplicativo</h3>
          <p className="mt-1 text-xs leading-5 text-muted">
            A nova conta será vinculada ao aplicativo escolhido. As contas já conectadas não mudam.
          </p>
        </div>
        <button
          aria-label="Fechar"
          className="btn-ghost !min-h-9 !px-2.5"
          disabled={connect.isPending}
          onClick={onClose}
          type="button"
        >
          <X size={16} />
        </button>
      </div>
      {apps.isLoading && (
        <div className="space-y-2.5" aria-busy="true" aria-label="Carregando aplicativos">
          {[0, 1].map((item) => (
            <div className="skeleton h-[72px]" key={item} />
          ))}
        </div>
      )}

      {apps.error && (
        <div className="flex items-start gap-3 rounded-xl border border-danger/30 bg-danger-soft/80 p-4 text-sm text-danger">
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
          <Smartphone className="mx-auto text-accent" size={22} />
          <p className="mt-3 text-sm text-fg-2">Nenhum aplicativo Meta configurado.</p>
          {apps.data.can_manage ? (
            <Link className="btn-secondary mt-4" onClick={onClose} to="/feature/meta-apps">
              Configurar aplicativo Meta
            </Link>
          ) : (
            <p className="mt-1 text-xs text-muted">Peça ao responsável do workspace para configurar.</p>
          )}
        </div>
      )}

      {appList.length > 0 && (
        <ul className="grid gap-3 md:grid-cols-2">
          {appList.map((app) => {
            const isPending = pendingAppId === app.id && connect.isPending;
            const empty = app.connected_accounts === 0;
            return (
              <li key={app.id}>
                <button
                  className="group flex w-full items-center gap-3 rounded-2xl border border-line bg-surface p-4 text-left transition-shadow hover:text-accent active:shadow-none disabled:cursor-wait disabled:opacity-60"
                  disabled={connect.isPending}
                  onClick={() => connect.mutate(app.id)}
                  type="button"
                >
                  <span className="grid size-10 shrink-0 place-items-center rounded-xl border border-line bg-brand-soft text-sm font-semibold text-accent">
                    {app.display_name.slice(0, 1).toUpperCase()}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex flex-wrap items-center gap-2">
                      <span className="truncate font-medium text-fg">{app.display_name}</span>
                      {app.is_selected && (
                        <span className="rounded-full bg-brand/15 px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.08em] text-accent">
                          Padrão
                        </span>
                      )}
                    </span>
                    <span className="mt-1 block truncate text-xs text-muted">App ID {app.app_id}</span>
                    <span
                      className={`mt-2 inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium ${
                        empty
                          ? "bg-warning/10 text-warning"
                          : "bg-success/10 text-success"
                      }`}
                    >
                      <span className={`size-1.5 rounded-full ${empty ? "bg-warning" : "bg-success"}`} />
                      {connectedLabel(app.connected_accounts)}
                    </span>
                  </span>
                  {isPending ? (
                    <LoaderCircle className="shrink-0 animate-spin text-accent" size={18} />
                  ) : (
                    <ArrowUpRight
                      className="shrink-0 text-muted transition group-hover:text-accent"
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
        <p className="mt-3 rounded-xl border border-danger/30 bg-danger-soft/80 px-4 py-3 text-sm text-danger" role="alert">
          Não foi possível iniciar a conexão. Tente novamente.
        </p>
      )}
    </section>
  );
}
