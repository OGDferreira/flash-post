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
import { ProfileLink } from "@/components/ProfileLink";
import {
  ConnectAppsPanel,
  canConnect,
  metaAppsQueryKey,
  type InstagramMetaAppsResponse,
} from "@/components/ConnectAccountModal";
import {
  formatAccountConnectedAt,
  formatConnectedDuration,
} from "@/features/instagram/accountDates";
import { ApiError, apiRequest } from "@/services/api";
import { useAuth } from "@/features/auth/AuthProvider";
import { confirmAction } from "@/lib/confirm";

type InstagramAccount = {
  id: string;
  profile_folder_id: string | null;
  username: string;
  profile_picture_url: string | null;
  token_expires_at: string;
  connected_at: string;
  connected_by_name?: string | null;
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
  const [showAllAccounts, setShowAllAccounts] = useState(false);
  const [accountFilter, setAccountFilter] = useState<"active" | "issues">("active");
  const [accountSearch, setAccountSearch] = useState("");
  const [accountSort, setAccountSort] = useState<
    "connection_asc" | "disconnection_desc" | "connection_desc"
  >("connection_desc");
  const [selectedFolderId, setSelectedFolderId] = useState("all");
  const [showAppSelector, setShowAppSelector] = useState(() => searchParams.get("connect") === "1");
  const accounts = useQuery({
    queryKey: ["instagram", "accounts"],
    queryFn: () => apiRequest<InstagramAccountsResponse>("/api/instagram/accounts"),
    refetchInterval: 120_000,
    retry: false,
  });
  const metaApps = useQuery({
    queryKey: metaAppsQueryKey,
    queryFn: () => apiRequest<InstagramMetaAppsResponse>("/api/instagram/apps"),
    // Load in parallel with the accounts list (it used to wait for it, delaying the connect flow).
    staleTime: 60_000,
    retry: false,
  });
  const folders = useQuery({
    queryKey: ["instagram", "folders"],
    queryFn: () => apiRequest<ProfileFoldersResponse>("/api/instagram/folders?include_accounts=false"),
    retry: false,
  });
  const startConnection = () => setShowAppSelector(true);
  useEffect(() => {
    if (searchParams.get("connect") !== "1") return;
    const next = new URLSearchParams(searchParams);
    next.delete("connect");
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);
  const disconnect = useMutation({
    mutationFn: (accountId: string) =>
      apiRequest<InstagramDisconnectResponse>(`/api/instagram/accounts/${accountId}`, {
        method: "DELETE",
      }),
    onSuccess: ({ meta_revoked }) => {
      setDisconnectMessage({
        complete: meta_revoked,
        text: meta_revoked
          ? "Conta desconectada do Flash e autorização revogada no Instagram."
          : "Conta removida do Flash, mas a Meta não confirmou a revogação. Remova o Flash dos apps conectados nas configurações do Instagram para concluir.",
      });
      void queryClient.invalidateQueries({ queryKey: ["instagram", "accounts"] });
      void queryClient.invalidateQueries({ queryKey: ["loops"] });
      void queryClient.invalidateQueries({ queryKey: ["instagram", "folders"] });
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
          ? "A conta com erro foi removida do Flash e a autorização foi revogada no Instagram."
          : "A conta com erro foi removida do Flash, mas a Meta não confirmou a revogação. Remova o Flash dos apps conectados nas configurações do Instagram.",
      });
      void queryClient.invalidateQueries({ queryKey: ["instagram", "accounts"] });
      void queryClient.invalidateQueries({ queryKey: ["loops"] });
      void queryClient.invalidateQueries({ queryKey: ["instagram", "folders"] });
    },
  });
  const removeBroken = useMutation({
    mutationFn: () =>
      apiRequest<{ removed: number; meta_revoked: number }>("/api/instagram/accounts/remove-broken", {
        method: "POST",
      }),
    onSuccess: ({ removed, meta_revoked }) => {
      setDisconnectMessage({
        complete: removed === 0 || meta_revoked === removed,
        text:
          removed === 0
            ? "Nenhuma conta com erro ou desconectada para remover."
            : `${removed} conta(s) com erro ou desconectada(s) removida(s) do Flash.` +
              (meta_revoked === removed
                ? " Autorização revogada no Instagram."
                : ` A Meta confirmou a revogação de ${meta_revoked}. Remova o Flash dos apps conectados nas configurações do Instagram para concluir as demais.`),
      });
      void queryClient.invalidateQueries({ queryKey: ["instagram", "accounts"] });
      void queryClient.invalidateQueries({ queryKey: ["loops"] });
      void queryClient.invalidateQueries({ queryKey: ["instagram", "folders"] });
    },
  });

  useEffect(() => {
    const outcome = searchParams.get("instagram");
    if (!outcome) return;
    const account = searchParams.get("account");
    if (outcome === "connected" && account) {
      setCallbackMessage({ text: `@${account} conectada ao workspace.`, kind: "success" });
    } else {
      setCallbackMessage(callbackMessages[outcome]);
    }
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

  const connectPanel = showAppSelector ? (
    <ConnectAppsPanel onClose={() => setShowAppSelector(false)} returnTo="/feature/accounts" />
  ) : null;
  if (accounts.isLoading) {
    return (
      <div className="mx-auto max-w-6xl space-y-5">
        {connectPanel}
        <LoadingState label="Carregando contas Instagram" />
      </div>
    );
  }
  if (accounts.error || !accounts.data) {
    return (
      <div className="mx-auto max-w-6xl space-y-5">
        {connectPanel}
        <ErrorState message="Não foi possível carregar as contas deste workspace." />
      </div>
    );
  }

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
  const removeBrokenError =
    removeBroken.error instanceof ApiError
      ? removeBroken.error.message
      : removeBroken.error
        ? "Não foi possível remover as contas com erro ou desconectadas."
        : null;
  const activeAccountCount = accounts.data.accounts.filter(isInstagramAccountActive).length;
  const issueAccountCount = accounts.data.accounts.length - activeAccountCount;
  // Only error/disconnected accounts are hard-removed in bulk (expired-but-connected are left to reconnect).
  const brokenAccountCount = accounts.data.accounts.filter(
    (account) => account.status === "error" || account.status === "disconnected",
  ).length;
  const unassignedAccountCount = accounts.data.accounts.filter(
    (account) => !account.profile_folder_id && isInstagramAccountActive(account),
  ).length;
  const visibleAccounts = accounts.data.accounts
    .filter((account) => {
      const active = isInstagramAccountActive(account);
      const matchesFilter = accountFilter === "active" ? active : !active;
      const matchesFolder =
        accountFilter === "issues" ||
        selectedFolderId === "all" ||
        (selectedFolderId === "unassigned"
          ? !account.profile_folder_id
          : account.profile_folder_id === selectedFolderId);
      return (
        matchesFilter &&
        matchesFolder &&
        account.username.toLowerCase().includes(accountSearch.toLowerCase())
      );
    })
    .sort((first, second) => {
      const connectedAt = (account: typeof first) => new Date(account.connected_at).getTime();
      const errorAt = (account: typeof first) =>
        account.error_at ? new Date(account.error_at).getTime() : Number.NEGATIVE_INFINITY;
      if (accountSort === "disconnection_desc") {
        return errorAt(second) - errorAt(first) || connectedAt(first) - connectedAt(second);
      }
      return accountSort === "connection_desc"
        ? connectedAt(second) - connectedAt(first)
        : connectedAt(first) - connectedAt(second);
    });

  // Render only the first rows by default: with hundreds of accounts (each with a photo) the
  // page would otherwise be heavy and slow. "Mostrar todas" loads the rest.
  const ACCOUNTS_PREVIEW = 12; // 4 rows × 3 columns at the widest layout
  const shownAccounts = showAllAccounts ? visibleAccounts : visibleAccounts.slice(0, ACCOUNTS_PREVIEW);
  const hiddenAccountCount = visibleAccounts.length - shownAccounts.length;

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <header>
        <div className="mt-2 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-2xl font-semibold tracking-[-0.045em] text-fg sm:text-3xl">
              Hub de Contas
            </h2>
          </div>
          {accounts.data.can_connect && (
            <div className="flex flex-col items-end gap-2">
              <button
                className="btn-primary"
                type="button"
                onClick={startConnection}
              >
                <Link2 size={16} />
                Conectar conta
              </button>
              {accounts.data.can_manage &&
                !metaApps.data?.platform?.available &&
                !metaApps.data?.apps.length &&
                !metaApps.isLoading &&
                !metaApps.error && (
                <Link
                  className="text-xs text-accent hover:text-white"
                  to="/feature/meta-apps"
                >
                  Configurar aplicativo Meta
                </Link>
              )}
            </div>
          )}
        </div>
      </header>

      {connectPanel}

      {callbackMessage && (
        <div
          className={`rounded-lg border px-4 py-3 text-sm ${
            callbackMessage.kind === "success"
              ? "border-success/30 bg-success-soft text-success"
              : callbackMessage.kind === "error"
                ? "border-danger/30 bg-danger-soft text-danger"
                : "border-line bg-surface-raised text-fg-2"
          }`}
          role="status"
        >
          {callbackMessage.text}
        </div>
      )}
      {disconnectError && <ErrorState message={disconnectError} />}
      {removeError && <ErrorState message={removeError} />}
      {removeBrokenError && <ErrorState message={removeBrokenError} />}
      {metaAppsError && <ErrorState message={metaAppsError} />}
      {disconnectMessage && (
        <div
          className={`rounded-lg border px-4 py-3 text-sm ${
            disconnectMessage.complete
              ? "border-success/30 bg-success-soft text-success"
              : "border-warning/30 bg-warning-soft text-warning"
          }`}
          role="status"
        >
          {disconnectMessage.text}
        </div>
      )}

      {!accounts.data.can_manage && !accounts.data.can_connect && (
        <p className="rounded-lg border border-line bg-surface-raised px-4 py-3 text-sm text-fg-2">
          Você pode ver as contas conectadas. Somente o OWNER do workspace pode gerenciá-las.
        </p>
      )}

      <section className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-xl border border-success/30 bg-success-soft p-4">
            <p className="text-xs uppercase tracking-wide text-success">Conectadas e ativas</p>
            <p className="mt-1 text-2xl font-semibold text-success">{activeAccountCount}</p>
          </div>
          <div className="rounded-xl border border-danger/30 bg-warning-soft p-4">
            <p className="text-xs uppercase tracking-wide text-warning">Precisam de atenção</p>
            <p className="mt-1 text-2xl font-semibold text-warning">{issueAccountCount}</p>
          </div>
        </div>
        {folders.error && (
          <p className="text-sm text-danger">Não foi possível carregar a organização por pastas.</p>
        )}
        <section
          aria-label="Quantidade de contas por pasta"
          className="rounded-xl border border-line bg-surface p-4"
        >
          <div className="mb-3 flex items-center gap-2">
            <Folder size={15} className="text-accent" />
            <h3 className="text-sm font-medium text-fg">Contas por pasta</h3>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              className={`rounded-full border px-3 py-1.5 text-xs ${
                selectedFolderId === "all"
                  ? "border-brand bg-brand-soft text-white"
                  : "border-line text-muted"
              }`}
              onClick={() => setSelectedFolderId("all")}
              type="button"
            >
              Todas ({activeAccountCount})
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
                      ? "bg-brand-soft text-white"
                      : "text-fg-2"
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
                  ? "border-brand bg-brand-soft text-white"
                  : "border-line text-muted"
              }`}
              onClick={() => setSelectedFolderId("unassigned")}
              type="button"
            >
              Sem pasta ({unassignedAccountCount})
            </button>
          </div>
        </section>
        <div className="flex flex-col gap-3 sm:flex-row">
          <label className="flex min-h-11 flex-1 items-center gap-2 rounded-lg border border-line bg-surface px-3 text-muted">
            <Search size={16} />
            <input
              className="w-full bg-transparent text-sm text-fg outline-none placeholder:text-muted"
              value={accountSearch}
              onChange={(event) => setAccountSearch(event.target.value)}
              placeholder="Buscar por usuário..."
              aria-label="Buscar conta Instagram por usuário"
            />
          </label>
          <select
            className="min-h-11 rounded-lg border border-line bg-surface px-3 text-xs text-fg outline-none"
            value={accountSort}
            onChange={(event) => setAccountSort(event.target.value as typeof accountSort)}
            aria-label="Ordenar contas Instagram"
          >
            <option value="connection_asc">Ordem de Conexão (mais antigas primeiro)</option>
            <option value="disconnection_desc">Ordem de Desconexão (caíram recentemente)</option>
            <option value="connection_desc">Recém-Conectadas (mais novas primeiro)</option>
          </select>
          <div className="flex rounded-lg border border-line bg-surface p-1">
            {([
              ["active", `Ativas (${activeAccountCount})`],
              ["issues", `Aba Oculta de Erros (${issueAccountCount})`],
            ] as const).map(([filter, label]) => (
              <button
                className={`rounded-md px-3 py-2 text-xs font-medium transition ${
                  accountFilter === filter
                    ? "bg-brand text-white"
                    : "text-muted hover:text-white"
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
        <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-muted">
          <h3>Contas Instagram ({visibleAccounts.length})</h3>
          <div className="flex items-center gap-3">
            {issueAccountCount > 0 && (
              <span className="text-xs text-danger">{issueAccountCount} com erro ou expiradas</span>
            )}
            {accounts.data.can_manage && brokenAccountCount > 0 && (
              <button
                className="inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-danger/30 px-3 py-1.5 text-xs font-medium text-danger transition hover:bg-danger-soft disabled:opacity-60"
                type="button"
                disabled={removeBroken.isPending}
                onClick={async () => {
                  if (
                    await confirmAction(
                      `Remover as ${brokenAccountCount} conta(s) com erro ou desconectada(s) do Flash? As contas e o histórico de publicações associado serão excluídos. As contas ativas não são afetadas.`,
                    )
                  ) {
                    removeBroken.mutate();
                  }
                }}
              >
                <Trash2 size={14} />
                {removeBroken.isPending ? "Removendo…" : `Remover com erro/desconectadas (${brokenAccountCount})`}
              </button>
            )}
          </div>
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
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {shownAccounts.map((account) => {
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
                className={`flex flex-col justify-between gap-3 rounded-xl border p-4 ${
                  active ? "border-success/30 bg-success-soft"                   : "border-danger/30 bg-danger-soft"
                }`}
                key={account.id}
              >
                <div className="flex min-w-0 items-center gap-3">
                  <InstagramAvatar
                    className={`size-11 rounded-xl border object-cover ${
                      active
                        ? "border-success/30 bg-success-soft text-success"
                        : "border-danger/30 bg-danger-soft text-danger"
                    }`}
                    src={account.profile_picture_url}
                    username={account.username}
                  />
                  <div className="min-w-0">
                    <p className="flex min-w-0 items-center gap-2 font-medium text-fg">
                      <span className="truncate">@{account.username}</span>
                      <ProfileLink username={account.username} />
                    </p>
                    <p
                      className={`mt-1 flex items-center gap-1.5 text-xs ${
                        active ? "text-success"                         : "text-danger"
                      }`}
                    >
                      {active ? <Check size={13} /> : <Clock3 size={13} />}
                      {label}
                    </p>
                    <p className="mt-1 text-xs text-muted">
                      Conectada em {formatAccountConnectedAt(account.connected_at)}
                      {account.connected_by_name ? ` · por ${account.connected_by_name}` : ""}
                    </p>
                    {account.status === "error" && (
                      <p className="mt-1 text-xs text-danger">
                        Permaneceu conectada por{" "}
                        {formatConnectedDuration(account.connected_at, account.error_at)} antes do erro
                      </p>
                    )}
                  </div>
                </div>
                {(accounts.data.can_connect || accounts.data.can_manage) && (
                  <div className="flex flex-wrap gap-2">
                    {!active && accounts.data.can_connect && (
                      <button
                        className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-brand px-3 py-2 text-sm text-white disabled:opacity-60"
                        type="button"
                        onClick={startConnection}
                        disabled={!canConnect(metaApps.data)}
                      >
                        <Link2 size={15} />
                        Reconectar
                      </button>
                    )}
                    {account.status === "connected" && accounts.data.can_manage && (
                      <button
                        className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg border border-danger/30 px-3 py-2 text-sm text-danger transition hover:bg-danger-soft disabled:opacity-60"
                        type="button"
                        disabled={disconnect.isPending}
                        onClick={async () => {
                          if (
                            await confirmAction(
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
                        className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg border border-danger/30 px-3 py-2 text-sm text-danger transition hover:bg-danger-soft disabled:opacity-60"
                        type="button"
                        disabled={removeErroredAccount.isPending}
                        onClick={async () => {
                          if (
                            await confirmAction(
                              `Remover @${account.username} do Flash? A conta e o histórico de publicações associado serão excluídos.`,
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
          })}
          </div>
        )}
        {hiddenAccountCount > 0 && (
          <div className="mt-3 flex justify-center">
            <button
              className="inline-flex items-center gap-2 rounded-lg border border-line px-4 py-2 text-sm font-medium text-fg-2 transition hover:border-brand hover:text-fg"
              onClick={() => setShowAllAccounts(true)}
              type="button"
            >
              Mostrar todas (+{hiddenAccountCount})
            </button>
          </div>
        )}
        {showAllAccounts && visibleAccounts.length > ACCOUNTS_PREVIEW && (
          <div className="mt-3 flex justify-center">
            <button
              className="text-sm font-medium text-muted transition hover:text-fg"
              onClick={() => setShowAllAccounts(false)}
              type="button"
            >
              Mostrar menos
            </button>
          </div>
        )}
      </section>

      <p className="text-xs leading-5 text-muted">
        Contas desconectadas e contas em erro ficam fora do fluxo ativo e permanecem visíveis para
        que você possa reconectá-las.
      </p>
    </div>
  );
}
