import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  Clock3,
  Link2,
  Search,
  Unlink,
} from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";

import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { InstagramAvatar } from "@/components/InstagramAvatar";
import { ApiError, apiRequest } from "@/services/api";

type InstagramAccount = {
  id: string;
  username: string;
  profile_picture_url: string | null;
  token_expires_at: string;
  connected_at: string;
  status: "connected" | "disconnected";
};

type InstagramAccountsResponse = {
  can_manage: boolean;
  accounts: InstagramAccount[];
};

type InstagramMetaAppsResponse = {
  selected_app_id: string | null;
};

type InstagramDisconnectResponse = {
  meta_revoked: boolean;
};

const callbackMessages: Record<string, { text: string; kind: "success" | "error" | "info" }> = {
  connected: { text: "Conta profissional conectada ao workspace.", kind: "success" },
  cancelled: { text: "A autorização foi cancelada. Nenhuma conta foi conectada.", kind: "info" },
  error: {
    text: "Não foi possível conectar a conta. Confira as permissões e tente novamente.",
    kind: "error",
  },
};

function isInstagramAccountActive(account: InstagramAccount): boolean {
  return account.status === "connected" && new Date(account.token_expires_at).getTime() > Date.now();
}

export function InstagramAccountsPage() {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [callbackMessage, setCallbackMessage] = useState<
    { text: string; kind: "success" | "error" | "info" } | undefined
  >();
  const [disconnectMessage, setDisconnectMessage] = useState<
    { text: string; complete: boolean } | undefined
  >();
  const [accountFilter, setAccountFilter] = useState<"active" | "issues" | "all">("active");
  const [accountSearch, setAccountSearch] = useState("");
  const accounts = useQuery({
    queryKey: ["instagram", "accounts"],
    queryFn: () => apiRequest<InstagramAccountsResponse>("/api/instagram/accounts"),
    refetchInterval: 60_000,
    retry: false,
  });
  const metaApps = useQuery({
    queryKey: ["instagram", "apps"],
    queryFn: () => apiRequest<InstagramMetaAppsResponse>("/api/instagram/apps"),
    enabled: accounts.data?.can_manage === true,
    retry: false,
  });
  const connect = useMutation({
    mutationFn: () =>
      apiRequest<{ authorization_url: string }>("/api/instagram/connect", { method: "POST" }),
    onSuccess: ({ authorization_url }) => window.location.assign(authorization_url),
  });
  const disconnect = useMutation({
    mutationFn: (accountId: string) =>
      apiRequest<InstagramDisconnectResponse>(`/api/instagram/accounts/${accountId}`, {
        method: "DELETE",
      }),
    onSuccess: ({ meta_revoked }) => {
      setDisconnectMessage({
        complete: meta_revoked,
        text: meta_revoked
          ? "Conta desconectada do FlashPost e autorização revogada no Instagram."
          : "Conta removida do FlashPost, mas a Meta não confirmou a revogação. Remova o FlashPost dos apps conectados nas configurações do Instagram para concluir.",
      });
      void queryClient.invalidateQueries({ queryKey: ["instagram", "accounts"] });
      void queryClient.invalidateQueries({ queryKey: ["loops"] });
    },
  });

  useEffect(() => {
    const outcome = searchParams.get("instagram");
    if (!outcome) return;
    setCallbackMessage(callbackMessages[outcome]);
    setSearchParams({}, { replace: true });
  }, [searchParams, setSearchParams]);

  if (accounts.isLoading) return <LoadingState label="Carregando contas Instagram" />;
  if (accounts.error || !accounts.data) {
    return <ErrorState message="Não foi possível carregar as contas deste workspace." />;
  }

  const connectError =
    connect.error instanceof ApiError
      ? connect.error.message
      : connect.error
        ? "Não foi possível iniciar a conexão com o Instagram."
        : null;
  const disconnectError =
    disconnect.error instanceof ApiError
      ? disconnect.error.message
      : disconnect.error
        ? "Não foi possível desconectar a conta."
        : null;
  const metaAppsError =
    metaApps.error instanceof ApiError
      ? metaApps.error.message
      : metaApps.error
        ? "Não foi possível carregar os aplicativos Meta."
        : null;
  const activeAccountCount = accounts.data.accounts.filter(isInstagramAccountActive).length;
  const issueAccountCount = accounts.data.accounts.length - activeAccountCount;
  const visibleAccounts = accounts.data.accounts.filter((account) => {
    const active = isInstagramAccountActive(account);
    const matchesFilter =
      accountFilter === "all" ||
      (accountFilter === "active" && active) ||
      (accountFilter === "issues" && !active);
    return matchesFilter && account.username.toLowerCase().includes(accountSearch.toLowerCase());
  });

  return (
    <div className="mx-auto max-w-4xl space-y-7">
      <header>
        <p className="text-xs font-medium uppercase tracking-[0.16em] text-[#7186ff]">Workspace</p>
        <div className="mt-2 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-2xl font-semibold tracking-[-0.045em] text-[#f5f7fb] sm:text-3xl">
              Hub de Contas
            </h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-[#94a3b8]">
              Acompanhe as contas profissionais conectadas e o estado de cada autorização.
            </p>
          </div>
          {accounts.data.can_manage && (
            <div className="flex flex-col items-end gap-2">
              <button
                className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-[#536dfe] px-4 py-2 text-sm font-medium text-white transition hover:bg-[#667eea] disabled:cursor-not-allowed disabled:opacity-60"
                type="button"
                onClick={() => connect.mutate()}
                disabled={!metaApps.data?.selected_app_id || metaApps.isLoading || connect.isPending}
              >
                <Link2 size={16} />
                {connect.isPending ? "Conectando..." : "Conectar conta"}
              </button>
              {!metaApps.data?.selected_app_id && !metaApps.isLoading && !metaApps.error && (
                <Link
                  className="text-xs text-[#aab7ff] hover:text-white"
                  to="/feature/settings"
                >
                  Configurar aplicativo Meta
                </Link>
              )}
            </div>
          )}
        </div>
      </header>

      {callbackMessage && (
        <div
          className={`rounded-lg border px-4 py-3 text-sm ${
            callbackMessage.kind === "success"
              ? "border-[#23513e] bg-[#0e1b17] text-[#9de0c0]"
              : callbackMessage.kind === "error"
                ? "border-[#47252d] bg-[#1a1013] text-[#f1a3ad]"
                : "border-[#27334a] bg-[#10141b] text-[#aeb9ce]"
          }`}
          role="status"
        >
          {callbackMessage.text}
        </div>
      )}
      {connectError && <ErrorState message={connectError} />}
      {disconnectError && <ErrorState message={disconnectError} />}
      {metaAppsError && <ErrorState message={metaAppsError} />}
      {disconnectMessage && (
        <div
          className={`rounded-lg border px-4 py-3 text-sm ${
            disconnectMessage.complete
              ? "border-[#23513e] bg-[#0e1b17] text-[#9de0c0]"
              : "border-[#6b552b] bg-[#1c180e] text-[#f2d48a]"
          }`}
          role="status"
        >
          {disconnectMessage.text}
        </div>
      )}

      {!accounts.data.can_manage && (
        <p className="rounded-lg border border-[#27334a] bg-[#10141b] px-4 py-3 text-sm text-[#aeb9ce]">
          Você pode ver as contas conectadas. Somente o OWNER do workspace pode gerenciá-las.
        </p>
      )}

      <section className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-xl border border-[#23513e] bg-[#0e1b17] p-4">
            <p className="text-xs uppercase tracking-wide text-[#76c8a0]">Conectadas e ativas</p>
            <p className="mt-1 text-2xl font-semibold text-[#b4f0d0]">{activeAccountCount}</p>
          </div>
          <div className="rounded-xl border border-[#6b3c2d] bg-[#1c1410] p-4">
            <p className="text-xs uppercase tracking-wide text-[#f2b884]">Precisam de atenção</p>
            <p className="mt-1 text-2xl font-semibold text-[#ffd1a8]">{issueAccountCount}</p>
          </div>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row">
          <label className="flex min-h-11 flex-1 items-center gap-2 rounded-lg border border-[#27334a] bg-[#0d1015] px-3 text-[#94a3b8]">
            <Search size={16} />
            <input
              className="w-full bg-transparent text-sm text-[#f5f7fb] outline-none placeholder:text-[#64748b]"
              value={accountSearch}
              onChange={(event) => setAccountSearch(event.target.value)}
              placeholder="Buscar por usuário..."
              aria-label="Buscar conta Instagram por usuário"
            />
          </label>
          <div className="flex rounded-lg border border-[#27334a] bg-[#0d1015] p-1">
            {([
              ["active", `Ativas (${activeAccountCount})`],
              ["issues", `Caídas (${issueAccountCount})`],
              ["all", `Todas (${accounts.data.accounts.length})`],
            ] as const).map(([filter, label]) => (
              <button
                className={`rounded-md px-3 py-2 text-xs font-medium transition ${
                  accountFilter === filter
                    ? "bg-[#536dfe] text-white"
                    : "text-[#94a3b8] hover:text-white"
                }`}
                key={filter}
                type="button"
                onClick={() => setAccountFilter(filter)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center justify-between text-sm text-[#94a3b8]">
          <h3>Contas Instagram ({visibleAccounts.length})</h3>
          {issueAccountCount > 0 && (
            <span className="text-xs text-[#f1a3ad]">{issueAccountCount} com erro ou expiradas</span>
          )}
        </div>
        {visibleAccounts.length === 0 ? (
          <EmptyState
            message={
              accounts.data.accounts.length === 0
                ? "Ainda não há contas Instagram conectadas a este workspace."
                : "Nenhuma conta corresponde a este filtro."
            }
          />
        ) : (
          visibleAccounts.map((account) => {
            const active = isInstagramAccountActive(account);
            const expired = new Date(account.token_expires_at).getTime() <= Date.now();
            const label =
              account.status === "disconnected"
                ? "Desconectada — conecte novamente para ativar"
                : expired
                  ? "Token expirado — reconecte a conta"
                  : `Ativa · token válido até ${new Date(account.token_expires_at).toLocaleDateString("pt-BR", {
                      timeZone: "America/Sao_Paulo",
                    })}`;

            return (
              <article
                className={`flex flex-col gap-4 rounded-xl border p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5 ${
                  active ? "border-[#23513e] bg-[#0e1b17]"                   : "border-[#47252d] bg-[#1a1013]"
                }`}
                key={account.id}
              >
                <div className="flex min-w-0 items-center gap-3">
                  <InstagramAvatar
                    className={`size-11 rounded-xl border object-cover ${
                      active
                        ? "border-[#23513e] bg-[#14251d] text-[#9de0c0]"
                        : "border-[#47252d] bg-[#211318] text-[#f1a3ad]"
                    }`}
                    src={account.profile_picture_url}
                    username={account.username}
                  />
                  <div className="min-w-0">
                    <p className="truncate font-medium text-[#f5f7fb]">@{account.username}</p>
                    <p
                      className={`mt-1 flex items-center gap-1.5 text-xs ${
                        active ? "text-[#9de0c0]"                         : "text-[#f1a3ad]"
                      }`}
                    >
                      {active ? <Check size={13} /> : <Clock3 size={13} />}
                      {label}
                    </p>
                  </div>
                </div>
                {accounts.data.can_manage && (
                  <div className="flex gap-2">
                    {!active && (
                      <button
                        className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-[#536dfe] px-3 py-2 text-sm text-white disabled:opacity-60"
                        type="button"
                        onClick={() => connect.mutate()}
                        disabled={connect.isPending || !metaApps.data?.selected_app_id}
                      >
                        <Link2 size={15} />
                        Reconectar
                      </button>
                    )}
                    {account.status === "connected" && (
                      <button
                        className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg border border-[#47252d] px-3 py-2 text-sm text-[#f1a3ad] transition hover:bg-[#1a1013] disabled:opacity-60"
                        type="button"
                        disabled={disconnect.isPending}
                        onClick={() => {
                          if (
                            window.confirm(
                              `Desconectar @${account.username}? A conta será mantida no hub como desconectada, mas o token salvo será apagado.`,
                            )
                          ) {
                            disconnect.mutate(account.id);
                          }
                        }}
                      >
                        <Unlink size={15} />
                        Desconectar
                      </button>
                    )}
                  </div>
                )}
              </article>
            );
          })
        )}
      </section>

      <p className="text-xs leading-5 text-[#64748b]">
        Contas desconectadas continuam visíveis no hub, mas os tokens são apagados do FlashPost.
        Tokens expirados precisam de nova autorização.
      </p>
    </div>
  );
}
