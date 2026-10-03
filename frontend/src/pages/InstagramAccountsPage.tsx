import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  Clock3,
  Instagram,
  Link2,
  Pencil,
  Plus,
  Save,
  Trash2,
  Unlink,
  X,
} from "lucide-react";
import { useSearchParams } from "react-router-dom";

import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { ApiError, apiRequest } from "@/services/api";

type InstagramAccount = {
  id: string;
  username: string;
  token_expires_at: string;
  connected_at: string;
};

type InstagramAccountsResponse = {
  can_manage: boolean;
  accounts: InstagramAccount[];
};

type InstagramMetaApp = {
  id: string;
  display_name: string;
  meta_app_name: string;
  app_id: string;
  category: string | null;
  app_link: string | null;
  is_selected: boolean;
  app_secret_configured: boolean;
};

type InstagramMetaAppsResponse = {
  can_manage: boolean;
  selected_app_id: string | null;
  apps: InstagramMetaApp[];
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

export function InstagramAccountsPage() {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [callbackMessage, setCallbackMessage] = useState<
    { text: string; kind: "success" | "error" | "info" } | undefined
  >();
  const [disconnectMessage, setDisconnectMessage] = useState<
    { text: string; complete: boolean } | undefined
  >();
  const [displayName, setDisplayName] = useState("");
  const [appId, setAppId] = useState("");
  const [appSecret, setAppSecret] = useState("");
  const [editingAppId, setEditingAppId] = useState<string | null>(null);
  const [editDisplayName, setEditDisplayName] = useState("");
  const [editAppSecret, setEditAppSecret] = useState("");
  const accounts = useQuery({
    queryKey: ["instagram", "accounts"],
    queryFn: () =>
      apiRequest<InstagramAccountsResponse>("/api/instagram/accounts"),
    retry: false,
  });
  const metaApps = useQuery({
    queryKey: ["instagram", "apps"],
    queryFn: () => apiRequest<InstagramMetaAppsResponse>("/api/instagram/apps"),
    enabled: accounts.data?.can_manage === true,
    retry: false,
  });
  const createMetaApp = useMutation({
    mutationFn: () =>
      apiRequest<{ app: InstagramMetaApp }>("/api/instagram/apps", {
        method: "POST",
        body: { display_name: displayName, app_id: appId, app_secret: appSecret },
      }),
    onSuccess: () => {
      setDisplayName("");
      setAppId("");
      setAppSecret("");
      void queryClient.invalidateQueries({ queryKey: ["instagram", "apps"] });
    },
  });
  const selectMetaApp = useMutation({
    mutationFn: (metaAppId: string) =>
      apiRequest(`/api/instagram/apps/${metaAppId}/select`, { method: "PUT" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["instagram", "apps"] });
    },
  });
  const updateMetaApp = useMutation({
    mutationFn: ({
      id,
      name,
      secret,
    }: {
      id: string;
      name: string;
      secret: string;
    }) =>
      apiRequest<InstagramMetaApp>(`/api/instagram/apps/${id}`, {
        method: "PATCH",
        body: {
          display_name: name,
          ...(secret.trim() ? { app_secret: secret } : {}),
        },
      }),
    onSuccess: () => {
      setEditingAppId(null);
      setEditDisplayName("");
      setEditAppSecret("");
      void queryClient.invalidateQueries({ queryKey: ["instagram", "apps"] });
    },
  });
  const removeMetaApp = useMutation({
    mutationFn: (metaAppId: string) =>
      apiRequest(`/api/instagram/apps/${metaAppId}`, { method: "DELETE" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["instagram", "apps"] });
    },
  });
  const connect = useMutation({
    mutationFn: () =>
      apiRequest<{ authorization_url: string }>("/api/instagram/connect", {
        method: "POST",
      }),
    onSuccess: ({ authorization_url }) => {
      window.location.assign(authorization_url);
    },
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
    },
  });

  useEffect(() => {
    const outcome = searchParams.get("instagram");
    if (!outcome) return;
    setCallbackMessage(callbackMessages[outcome]);
    setSearchParams({}, { replace: true });
  }, [searchParams, setSearchParams]);

  if (accounts.isLoading) {
    return <LoadingState label="Carregando contas Instagram" />;
  }
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
  const metaAppMutationError = [
    createMetaApp.error,
    selectMetaApp.error,
    updateMetaApp.error,
    removeMetaApp.error,
  ].find(Boolean);
  const metaAppMutationMessage =
    metaAppMutationError instanceof ApiError
      ? metaAppMutationError.message
      : metaAppMutationError
        ? "Não foi possível atualizar os aplicativos Meta."
        : null;

  return (
    <div className="mx-auto max-w-4xl space-y-7">
      <header>
        <p className="text-xs font-medium uppercase tracking-[0.16em] text-[#7186ff]">
          Workspace
        </p>
        <div className="mt-2 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-2xl font-semibold tracking-[-0.045em] text-[#f5f7fb] sm:text-3xl">
              Contas Instagram
            </h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-[#94a3b8]">
              Conecte contas profissionais para mantê-las disponíveis neste workspace.
              As publicações pelos Loops serão adicionadas em uma próxima fase.
            </p>
          </div>
          {accounts.data.can_manage && (
            <button
              className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-[#536dfe] px-4 py-2 text-sm font-medium text-white transition hover:bg-[#667eea] disabled:cursor-not-allowed disabled:opacity-60"
              type="button"
              onClick={() => connect.mutate()}
              disabled={
                !metaApps.data?.selected_app_id ||
                metaApps.isLoading ||
                connect.isPending
              }
            >
              <Link2 size={16} />
              {connect.isPending ? "Conectando..." : "Conectar conta"}
            </button>
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

      {accounts.data.can_manage && (
        <section className="space-y-5 rounded-xl border border-[#27334a] bg-[#0d1015] p-5 sm:p-6">
          <div>
            <h3 className="font-medium text-[#f5f7fb]">Aplicativos Meta</h3>
            <p className="mt-2 text-sm leading-6 text-[#94a3b8]">
              Cadastre e escolha qual aplicativo será usado para conectar novas contas. O segredo
              é validado na Meta e criptografado no servidor; nunca é exibido novamente.
            </p>
          </div>
          {metaApps.isLoading ? (
            <LoadingState label="Carregando aplicativos Meta" />
          ) : metaAppsError ? (
            <ErrorState message={metaAppsError} />
          ) : (
            <>
              {metaAppMutationMessage && <ErrorState message={metaAppMutationMessage} />}
              <div className="space-y-3">
                {metaApps.data?.apps.map((app) => (
                  <article
                    className={`space-y-4 rounded-lg border p-4 ${
                      app.is_selected
                        ? "border-[#536dfe] bg-[#11182d]"
                        : "border-[#27334a] bg-[#090b0f]"
                    }`}
                    key={app.id}
                  >
                    <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h4 className="font-medium text-[#f5f7fb]">{app.display_name}</h4>
                        {app.is_selected && (
                          <span className="rounded-full bg-[#26366f] px-2 py-0.5 text-xs text-[#c4ceff]">
                            Selecionado
                          </span>
                        )}
                      </div>
                      <p className="mt-1 text-sm text-[#94a3b8]">
                        {app.meta_app_name} · ID {app.app_id}
                      </p>
                      <p className="mt-1 text-xs text-[#64748b]">
                        {[app.category, app.app_link].filter(Boolean).join(" · ") ||
                          "Informações adicionais não fornecidas pela Meta"}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <button
                        className="grid size-10 place-items-center rounded-lg border border-[#27334a] text-[#cbd5e1] hover:bg-[#10141b]"
                        type="button"
                        aria-label={`Editar ${app.display_name}`}
                        onClick={() => {
                          setEditingAppId(app.id);
                          setEditDisplayName(app.display_name);
                          setEditAppSecret("");
                          updateMetaApp.reset();
                        }}
                      >
                        <Pencil size={15} />
                      </button>
                      {!app.is_selected && (
                        <button
                          className="min-h-10 rounded-lg border border-[#33447c] px-3 py-2 text-sm text-[#c4ceff] hover:bg-[#11182d] disabled:opacity-60"
                          type="button"
                          disabled={selectMetaApp.isPending}
                          onClick={() => selectMetaApp.mutate(app.id)}
                        >
                          Usar para novas conexões
                        </button>
                      )}
                      <button
                        className="grid size-10 place-items-center rounded-lg border border-[#47252d] text-[#f1a3ad] hover:bg-[#1a1013] disabled:opacity-60"
                        type="button"
                        aria-label={`Remover ${app.display_name}`}
                        disabled={removeMetaApp.isPending}
                        onClick={() => {
                          if (
                            window.confirm(
                              `Remover o aplicativo "${app.display_name}"? Apps com contas Instagram conectadas não podem ser removidos.`,
                            )
                          ) {
                            removeMetaApp.mutate(app.id);
                          }
                        }}
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>
                    </div>
                    {editingAppId === app.id && (
                      <form
                        className="grid gap-3 border-t border-[#27334a] pt-4 sm:grid-cols-2"
                        onSubmit={(event) => {
                          event.preventDefault();
                          updateMetaApp.mutate({
                            id: app.id,
                            name: editDisplayName,
                            secret: editAppSecret,
                          });
                        }}
                      >
                        <label className="grid gap-2 text-sm text-[#cbd5e1]">
                          Nome interno
                          <input
                            className="min-h-10 rounded-lg border border-[#27334a] bg-[#090b0f] px-3 text-[#f5f7fb] outline-none focus:border-[#7186ff]"
                            maxLength={120}
                            required
                            value={editDisplayName}
                            onChange={(event) => setEditDisplayName(event.target.value)}
                          />
                        </label>
                        <label className="grid gap-2 text-sm text-[#cbd5e1]">
                          Novo App Secret (opcional)
                          <input
                            autoComplete="new-password"
                            className="min-h-10 rounded-lg border border-[#27334a] bg-[#090b0f] px-3 text-[#f5f7fb] outline-none focus:border-[#7186ff]"
                            maxLength={512}
                            type="password"
                            value={editAppSecret}
                            onChange={(event) => setEditAppSecret(event.target.value)}
                            placeholder="Deixe vazio para manter o atual"
                          />
                        </label>
                        <div className="flex items-center gap-2 sm:col-span-2">
                          <button
                            className="inline-flex min-h-10 items-center gap-2 rounded-lg bg-[#536dfe] px-3 py-2 text-sm text-white disabled:opacity-60"
                            type="submit"
                            disabled={updateMetaApp.isPending || !editDisplayName.trim()}
                          >
                            <Save size={15} />
                            {updateMetaApp.isPending ? "Salvando..." : "Salvar alterações"}
                          </button>
                          <button
                            className="grid size-10 place-items-center rounded-lg border border-[#27334a] text-[#cbd5e1]"
                            type="button"
                            aria-label="Cancelar edição"
                            onClick={() => {
                              setEditingAppId(null);
                              setEditAppSecret("");
                              updateMetaApp.reset();
                            }}
                          >
                            <X size={15} />
                          </button>
                        </div>
                      </form>
                    )}
                  </article>
                ))}
                {metaApps.data?.apps.length === 0 && (
                  <p className="rounded-lg border border-dashed border-[#27334a] px-4 py-3 text-sm text-[#94a3b8]">
                    Nenhum aplicativo cadastrado. Adicione seu app Meta abaixo.
                  </p>
                )}
              </div>
              <form
                className="grid gap-4 border-t border-[#202838] pt-5 sm:grid-cols-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  createMetaApp.mutate();
                }}
              >
                <label className="grid gap-2 text-sm text-[#cbd5e1] sm:col-span-2">
                  Nome para identificar o aplicativo
                  <input
                    autoComplete="off"
                    className="min-h-10 rounded-lg border border-[#27334a] bg-[#090b0f] px-3 text-[#f5f7fb] outline-none focus:border-[#7186ff]"
                    maxLength={120}
                    required
                    value={displayName}
                    onChange={(event) => setDisplayName(event.target.value)}
                    placeholder="Ex.: App principal da marca"
                  />
                </label>
                <label className="grid gap-2 text-sm text-[#cbd5e1]">
                  ID do Aplicativo Meta
                  <input
                    autoComplete="off"
                    className="min-h-10 rounded-lg border border-[#27334a] bg-[#090b0f] px-3 text-[#f5f7fb] outline-none focus:border-[#7186ff]"
                    inputMode="numeric"
                    maxLength={64}
                    pattern="[0-9]+"
                    required
                    value={appId}
                    onChange={(event) => setAppId(event.target.value)}
                  />
                </label>
                <label className="grid gap-2 text-sm text-[#cbd5e1]">
                  Chave Secreta do Aplicativo
                  <input
                    autoComplete="new-password"
                    className="min-h-10 rounded-lg border border-[#27334a] bg-[#090b0f] px-3 text-[#f5f7fb] outline-none focus:border-[#7186ff]"
                    maxLength={512}
                    type="password"
                    required
                    value={appSecret}
                    onChange={(event) => setAppSecret(event.target.value)}
                    placeholder="Cole a chave secreta do app Meta"
                  />
                </label>
                <p className="text-xs leading-5 text-[#64748b] sm:col-span-2">
                  Ao cadastrar, o FlashPost consulta o nome e as informações públicas disponíveis
                  na Meta. O segredo não será retornado nem compartilhado com outros workspaces.
                </p>
                <div className="flex items-center gap-3 sm:col-span-2">
                  <button
                    className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-[#536dfe] px-4 py-2 text-sm font-medium text-white transition hover:bg-[#667eea] disabled:cursor-not-allowed disabled:opacity-60"
                    type="submit"
                    disabled={
                      createMetaApp.isPending ||
                      displayName.trim().length === 0 ||
                      appId.trim().length === 0 ||
                      appSecret.trim().length === 0
                    }
                  >
                    <Plus size={15} />
                    {createMetaApp.isPending ? "Validando e salvando..." : "Adicionar aplicativo"}
                  </button>
                </div>
              </form>
            </>
          )}
        </section>
      )}

      {!accounts.data.can_manage && (
        <p className="rounded-lg border border-[#27334a] bg-[#10141b] px-4 py-3 text-sm text-[#aeb9ce]">
          Você pode ver as contas conectadas. Somente o OWNER do workspace pode gerenciá-las.
        </p>
      )}

      <section className="space-y-3">
        <h3 className="text-sm font-medium text-[#cbd5e1]">
          Contas conectadas <span className="text-[#64748b]">({accounts.data.accounts.length})</span>
        </h3>
        {accounts.data.accounts.length === 0 ? (
          <EmptyState message="Ainda não há contas Instagram conectadas a este workspace." />
        ) : (
          accounts.data.accounts.map((account) => {
            const expiresAt = new Date(account.token_expires_at);
            const isExpired = expiresAt.getTime() <= Date.now();
            const expiryLabel = isExpired
              ? "Token expirado — reconecte a conta"
              : `Acesso válido até ${expiresAt.toLocaleDateString("pt-BR")}`;

            return (
              <article
                className="flex flex-col gap-4 rounded-xl border border-[#202838] bg-[#0d1015] p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5"
                key={account.id}
              >
                <div className="flex min-w-0 items-center gap-3">
                  <span className="grid size-11 shrink-0 place-items-center rounded-xl border border-[#33447c] bg-[#11182d] text-[#aab7ff]">
                    <Instagram size={19} />
                  </span>
                  <div className="min-w-0">
                    <p className="truncate font-medium text-[#f5f7fb]">
                      @{account.username}
                    </p>
                    <p className={`mt-1 flex items-center gap-1.5 text-xs ${isExpired ? "text-[#f1a3ad]" : "text-[#94a3b8]"}`}>
                      {isExpired ? <Clock3 size={13} /> : <Check size={13} />}
                      {expiryLabel}
                    </p>
                  </div>
                </div>
                {accounts.data.can_manage && (
                  <button
                    className="inline-flex min-h-10 items-center justify-center gap-2 self-start rounded-lg border border-[#47252d] px-3 py-2 text-sm text-[#f1a3ad] transition hover:bg-[#1a1013] disabled:opacity-60 sm:self-auto"
                    type="button"
                    disabled={disconnect.isPending}
                    onClick={() => {
                      if (
                        window.confirm(
                          `Desconectar @${account.username}? O FlashPost removerá o acesso salvo e tentará revogar a autorização no Instagram. Será preciso reconectar antes de publicar novamente.`,
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
              </article>
            );
          })
        )}
      </section>

      <p className="text-xs leading-5 text-[#64748b]">
        As contas ficam conectadas até um OWNER desconectá-las ou a autorização expirar/revogar.
        A Meta emite tokens de longa duração com validade limitada; a renovação automática será
        integrada ao fluxo de publicação dos Loops.
      </p>
    </div>
  );
}
