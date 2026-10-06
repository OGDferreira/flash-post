import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  Clock3,
  Folder,
  Link2,
  Search,
  Trash2,
  Unlink,
} from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";

import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { InstagramAvatar } from "@/components/InstagramAvatar";
import {
  formatAccountConnectedAt,
  formatConnectedDuration,
} from "@/features/instagram/accountDates";
import { ApiError, apiRequest } from "@/services/api";
import { useAuth } from "@/features/auth/AuthProvider";

type InstagramAccount = {
  id: string;
  profile_folder_id: string | null;
  username: string;
  profile_picture_url: string | null;
  token_expires_at: string;
  connected_at: string;
  error_at: string | null;
  status: "connected" | "disconnected" | "error";
};

type InstagramAccountsResponse = {
  can_manage: boolean;
  can_connect: boolean;
  accounts: InstagramAccount[];
};

type ProfileFoldersResponse = {
  folders: { id: string; name: string; color: string }[];
};

type InstagramMetaAppsResponse = {
  selected_app_id: string | null;
  can_manage: boolean;
  apps: { id: string; display_name: string; meta_app_name: string; app_id: string }[];
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
  const { user } = useAuth();
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
  const [selectedFolderId, setSelectedFolderId] = useState("all");
  const [showAppSelector, setShowAppSelector] = useState(false);
  const accounts = useQuery({
    queryKey: ["instagram", "accounts"],
    queryFn: () => apiRequest<InstagramAccountsResponse>("/api/instagram/accounts"),
    refetchInterval: 60_000,
    retry: false,
  });
  const metaApps = useQuery({
    queryKey: ["instagram", "apps"],
    queryFn: () => apiRequest<InstagramMetaAppsResponse>("/api/instagram/apps"),
    enabled: accounts.data?.can_connect === true,
    retry: false,
  });
  const folders = useQuery({
    queryKey: ["instagram", "folders"],
    queryFn: () => apiRequest<ProfileFoldersResponse>("/api/instagram/folders"),
    retry: false,
  });
  const connect = useMutation({
    mutationFn: (appId: string) =>
      apiRequest<{ authorization_url: string }>(
        `/api/instagram/connect?app_id=${encodeURIComponent(appId)}`,
        { method: "POST" },
      ),
    onSuccess: ({ authorization_url }) => window.location.assign(authorization_url),
  });
  const startConnection = () => setShowAppSelector(true);
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
  const removeErroredAccount = useMutation({
    mutationFn: (accountId: string) =>
      apiRequest<InstagramDisconnectResponse>(`/api/instagram/accounts/${accountId}/remove`, {
        method: "DELETE",
      }),
    onSuccess: ({ meta_revoked }) => {
      setDisconnectMessage({
        complete: meta_revoked,
        text: meta_revoked
          ? "A conta com erro foi removida do FlashPost e a autorização foi revogada no Instagram."
          : "A conta com erro foi removida do FlashPost, mas a Meta não confirmou a revogação. Remova o FlashPost dos apps conectados nas configurações do Instagram.",
      });
      void queryClient.invalidateQueries({ queryKey: ["instagram", "accounts"] });
      void queryClient.invalidateQueries({ queryKey: ["loops"] });
      void queryClient.invalidateQueries({ queryKey: ["instagram", "folders"] });
    },
  });

  useEffect(() => {
    const outcome = searchParams.get("instagram");
    if (!outcome) return;
    setCallbackMessage(callbackMessages[outcome]);
    if (outcome === "connected") {
      void queryClient.invalidateQueries({ queryKey: ["instagram", "accounts"] });
      void queryClient.invalidateQueries({ queryKey: ["analytics"] });
      void queryClient.invalidateQueries({ queryKey: ["collaborators"] });
      if (user?.role === "COLLABORATOR") {
        window.dispatchEvent(
          new CustomEvent("flashpost-toast", {
            detail: "Conexão concluída! Mais uma conta na sua jornada. Continue assim!",
          }),
        );
      }
    }
    setSearchParams({}, { replace: true });
  }, [queryClient, searchParams, setSearchParams, user?.role]);

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
  const removeError =
    removeErroredAccount.error instanceof ApiError
      ? removeErroredAccount.error.message
      : removeErroredAccount.error
        ? "Não foi possível remover a conta com erro."
        : null;
  const metaAppsError =
    metaApps.error instanceof ApiError
      ? metaApps.error.message
      : metaApps.error
        ? "Não foi possível carregar os aplicativos Meta."
        : null;
  const activeAccountCount = accounts.data.accounts.filter(isInstagramAccountActive).length;
  const issueAccountCount = accounts.data.accounts.length - activeAccountCount;
  const unassignedAccountCount = accounts.data.accounts.filter(
    (account) => !account.profile_folder_id && isInstagramAccountActive(account),
  ).length;
  const visibleAccounts = accounts.data.accounts.filter((account) => {
    const active = isInstagramAccountActive(account);
    const matchesFilter =
      accountFilter === "all" ||
      (accountFilter === "active" && active) ||
      (accountFilter === "issues" && !active);
    const matchesFolder =
      selectedFolderId === "all" ||
      (selectedFolderId === "unassigned"
        ? !account.profile_folder_id
        : account.profile_folder_id === selectedFolderId);
    return (
      matchesFilter &&
      matchesFolder &&
      account.username.toLowerCase().includes(accountSearch.toLowerCase())
    );
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
          {accounts.data.can_connect && (
            <div className="flex flex-col items-end gap-2">
              <button
                className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-[#536dfe] px-4 py-2 text-sm font-medium text-white transition hover:bg-[#667eea] disabled:cursor-not-allowed disabled:opacity-60"
                type="button"
                onClick={startConnection}
                disabled={
                  !metaApps.data?.apps.length ||
                  metaApps.isLoading ||
                  connect.isPending
                }
              >
                <Link2 size={16} />
                {connect.isPending ? "Conectando..." : "Conectar conta"}
              </button>
              {accounts.data.can_manage &&
                !metaApps.data?.apps.length &&
                !metaApps.isLoading &&
                !metaApps.error && (
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

      {showAppSelector && (
        <section className="space-y-3 rounded-xl border border-[#27334a] bg-[#0d1015] p-4">
          <div>
            <h3 className="font-medium text-[#f5f7fb]">Escolha o aplicativo Meta</h3>
            <p className="mt-1 text-sm text-[#94a3b8]">
              A nova conta será vinculada ao app selecionado. As contas existentes não serão alteradas.
            </p>
          </div>
          {metaApps.data?.apps.map((app) => (
            <button
              className="flex w-full flex-col rounded-lg border border-[#27334a] bg-[#090b0f] p-3 text-left transition hover:border-[#536dfe] sm:flex-row sm:items-center sm:justify-between"
              key={app.id}
              type="button"
              disabled={connect.isPending}
              onClick={() => connect.mutate(app.id)}
            >
              <span className="font-medium text-[#f5f7fb]">{app.display_name}</span>
              <span className="mt-1 text-xs text-[#94a3b8] sm:mt-0">
                {app.meta_app_name} · ID {app.app_id}
              </span>
            </button>
          ))}
          <button
            className="text-sm text-[#aab7ff] hover:text-white"
            type="button"
            onClick={() => setShowAppSelector(false)}
          >
            Cancelar
          </button>
        </section>
      )}

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
      {removeError && <ErrorState message={removeError} />}
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

      {!accounts.data.can_manage && !accounts.data.can_connect && (
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
        {folders.error && (
          <p className="text-sm text-[#f1a3ad]">Não foi possível carregar a organização por pastas.</p>
        )}
        <section
          aria-label="Quantidade de contas por pasta"
          className="rounded-xl border border-[#27334a] bg-[#0d1015] p-4"
        >
          <div className="mb-3 flex items-center gap-2">
            <Folder size={15} className="text-[#aab7ff]" />
            <h3 className="text-sm font-medium text-[#e6eaf2]">Contas por pasta</h3>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              className={`rounded-full border px-3 py-1.5 text-xs ${
                selectedFolderId === "all"
                  ? "border-[#536dfe] bg-[#151b2d] text-white"
                  : "border-[#27334a] text-[#94a3b8]"
              }`}
              onClick={() => setSelectedFolderId("all")}
              type="button"
            >
              Todas ({accounts.data.accounts.length})
            </button>
            {(folders.data?.folders ?? []).map((folder) => {
              const count = accounts.data.accounts.filter(
                (account) =>
                  account.profile_folder_id === folder.id &&
                  isInstagramAccountActive(account),
              ).length;
              return (
                <button
                  className={`rounded-full border px-3 py-1.5 text-xs ${
                    selectedFolderId === folder.id
                      ? "bg-[#151b2d] text-white"
                      : "text-[#cbd5e1]"
                  }`}
                  key={folder.id}
                  onClick={() => setSelectedFolderId(folder.id)}
                  style={{ borderColor: folder.color }}
                  type="button"
                >
                  <span aria-hidden="true" className="mr-1.5" style={{ color: folder.color }}>
                    ●
                  </span>
                  {folder.name} ({count})
                </button>
              );
            })}
            <button
              className={`rounded-full border px-3 py-1.5 text-xs ${
                selectedFolderId === "unassigned"
                  ? "border-[#536dfe] bg-[#151b2d] text-white"
                  : "border-[#27334a] text-[#94a3b8]"
              }`}
              onClick={() => setSelectedFolderId("unassigned")}
              type="button"
            >
              Sem pasta ({unassignedAccountCount})
            </button>
          </div>
        </section>
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
              ["issues", `Com erro (${issueAccountCount})`],
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
                : account.status === "error"
                  ? "Conta com erro — reconecte para reativar"
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
                    <p className="mt-1 text-xs text-[#94a3b8]">
                      Conectada em {formatAccountConnectedAt(account.connected_at)}
                    </p>
                    {account.status === "error" && (
                      <p className="mt-1 text-xs text-[#f1a3ad]">
                        Permaneceu conectada por{" "}
                        {formatConnectedDuration(account.connected_at, account.error_at)} antes do erro
                      </p>
                    )}
                  </div>
                </div>
                {(accounts.data.can_connect || accounts.data.can_manage) && (
                  <div className="flex gap-2">
                    {!active && accounts.data.can_connect && (
                      <button
                        className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-[#536dfe] px-3 py-2 text-sm text-white disabled:opacity-60"
                        type="button"
                        onClick={startConnection}
                        disabled={
                          connect.isPending ||
                          !metaApps.data?.apps.length
                        }
                      >
                        <Link2 size={15} />
                        Reconectar
                      </button>
                    )}
                    {account.status === "connected" && accounts.data.can_manage && (
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
                    {account.status === "error" && accounts.data.can_manage && (
                      <button
                        className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg border border-[#47252d] px-3 py-2 text-sm text-[#f1a3ad] transition hover:bg-[#1a1013] disabled:opacity-60"
                        type="button"
                        disabled={removeErroredAccount.isPending}
                        onClick={() => {
                          if (
                            window.confirm(
                              `Remover @${account.username} do FlashPost? A conta e o histórico de publicações associado serão excluídos.`,
                            )
                          ) {
                            removeErroredAccount.mutate(account.id);
                          }
                        }}
                      >
                        <Trash2 size={15} />
                        Remover conta
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
        Contas desconectadas e contas em erro ficam fora do fluxo ativo e permanecem visíveis para
        que você possa reconectá-las.
      </p>
    </div>
  );
}
