import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Clock3, Instagram, Link2, Unlink } from "lucide-react";
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

type InstagramAppSettings = {
  configured: boolean;
  app_id: string | null;
  app_secret_configured: boolean;
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
  const [appId, setAppId] = useState("");
  const [appSecret, setAppSecret] = useState("");
  const accounts = useQuery({
    queryKey: ["instagram", "accounts"],
    queryFn: () =>
      apiRequest<InstagramAccountsResponse>("/api/instagram/accounts"),
    retry: false,
  });
  const appSettings = useQuery({
    queryKey: ["instagram", "app-settings"],
    queryFn: () => apiRequest<InstagramAppSettings>("/api/instagram/app-settings"),
    enabled: accounts.data?.can_manage === true,
    retry: false,
  });
  const saveAppSettings = useMutation({
    mutationFn: () =>
      apiRequest<InstagramAppSettings>("/api/instagram/app-settings", {
        method: "PUT",
        body: { app_id: appId, app_secret: appSecret || null },
      }),
    onSuccess: (settings) => {
      setAppId(settings.app_id ?? "");
      setAppSecret("");
      void queryClient.setQueryData(["instagram", "app-settings"], settings);
    },
  });
  const removeAppSettings = useMutation({
    mutationFn: () =>
      apiRequest<InstagramAppSettings>("/api/instagram/app-settings", {
        method: "DELETE",
      }),
    onSuccess: (settings) => {
      setAppId("");
      setAppSecret("");
      void queryClient.setQueryData(["instagram", "app-settings"], settings);
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

  useEffect(() => {
    if (appSettings.data) {
      setAppId(appSettings.data.app_id ?? "");
    }
  }, [appSettings.data]);

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
  const appSettingsError =
    appSettings.error instanceof ApiError
      ? appSettings.error.message
      : appSettings.error
        ? "Não foi possível carregar as configurações da aplicação Meta."
        : null;
  const saveAppSettingsError =
    saveAppSettings.error instanceof ApiError
      ? saveAppSettings.error.message
      : saveAppSettings.error
        ? "Não foi possível salvar as credenciais da aplicação Meta."
        : null;
  const removeAppSettingsError =
    removeAppSettings.error instanceof ApiError
      ? removeAppSettings.error.message
      : removeAppSettings.error
        ? "Não foi possível remover as credenciais da aplicação Meta."
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
                !appSettings.data?.configured ||
                appSettings.isLoading ||
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
        <section className="rounded-xl border border-[#27334a] bg-[#0d1015] p-5 sm:p-6">
          <h3 className="font-medium text-[#f5f7fb]">Aplicativo Meta do workspace</h3>
          <p className="mt-2 text-sm leading-6 text-[#94a3b8]">
            Informe o ID e a chave secreta do seu próprio app Meta. A chave é criptografada
            no servidor, nunca é exibida novamente e não é compartilhada com outros workspaces.
          </p>
          {appSettings.isLoading ? (
            <LoadingState label="Carregando configuração Meta" />
          ) : appSettingsError ? (
            <div className="mt-4"><ErrorState message={appSettingsError} /></div>
          ) : (
            <form
              className="mt-5 grid gap-4 sm:grid-cols-2"
              onSubmit={(event) => {
                event.preventDefault();
                saveAppSettings.mutate();
              }}
            >
              <label className="grid gap-2 text-sm text-[#cbd5e1]">
                ID do Aplicativo
                <input
                  autoComplete="off"
                  className="min-h-10 rounded-lg border border-[#27334a] bg-[#090b0f] px-3 text-[#f5f7fb] outline-none focus:border-[#7186ff] disabled:opacity-60"
                  inputMode="numeric"
                  maxLength={64}
                  pattern="[0-9]+"
                  required
                  value={appId}
                  onChange={(event) => setAppId(event.target.value)}
                  disabled={accounts.data.accounts.length > 0}
                  aria-describedby="instagram-app-id-help"
                />
                {accounts.data.accounts.length > 0 && (
                  <span id="instagram-app-id-help" className="text-xs text-[#94a3b8]">
                    Desconecte as contas antes de trocar o ID do app.
                  </span>
                )}
              </label>
              <label className="grid gap-2 text-sm text-[#cbd5e1]">
                Chave Secreta do Aplicativo
                <input
                  autoComplete="new-password"
                  className="min-h-10 rounded-lg border border-[#27334a] bg-[#090b0f] px-3 text-[#f5f7fb] outline-none focus:border-[#7186ff]"
                  maxLength={512}
                  type="password"
                  required={!appSettings.data?.app_secret_configured}
                  value={appSecret}
                  onChange={(event) => setAppSecret(event.target.value)}
                  placeholder={
                    appSettings.data?.app_secret_configured
                      ? "Configurada; preencha apenas para substituir"
                      : "Cole a chave secreta do app Meta"
                  }
                  aria-describedby="instagram-app-secret-help"
                />
                <span id="instagram-app-secret-help" className="text-xs text-[#94a3b8]">
                  Nunca use uma chave de outro app nem a envie pelo chat.
                </span>
              </label>
              {saveAppSettingsError && (
                <div className="sm:col-span-2"><ErrorState message={saveAppSettingsError} /></div>
              )}
              {removeAppSettingsError && (
                <div className="sm:col-span-2"><ErrorState message={removeAppSettingsError} /></div>
              )}
              {saveAppSettings.isSuccess && (
                <p className="text-sm text-[#9de0c0]" role="status">
                  Credenciais salvas com segurança para este workspace.
                </p>
              )}
              <div className="flex items-center gap-3 sm:col-span-2">
                <button
                  className="inline-flex min-h-10 items-center justify-center rounded-lg bg-[#536dfe] px-4 py-2 text-sm font-medium text-white transition hover:bg-[#667eea] disabled:cursor-not-allowed disabled:opacity-60"
                  type="submit"
                  disabled={
                    saveAppSettings.isPending ||
                    appId.trim().length === 0 ||
                    (!appSecret && !appSettings.data?.app_secret_configured)
                  }
                >
                  {saveAppSettings.isPending ? "Salvando..." : "Salvar credenciais"}
                </button>
                <span className="text-xs text-[#94a3b8]">
                  {appSettings.data?.configured
                    ? "App configurado"
                    : "Configure o app para habilitar a conexão"}
                </span>
                {appSettings.data?.app_secret_configured &&
                  accounts.data.accounts.length === 0 && (
                    <button
                      className="ml-auto min-h-10 rounded-lg border border-[#47252d] px-3 py-2 text-sm text-[#f1a3ad] transition hover:bg-[#1a1013] disabled:opacity-60"
                      type="button"
                      disabled={removeAppSettings.isPending}
                      onClick={() => {
                        if (
                          window.confirm(
                            "Remover o ID e o segredo do app Meta deste workspace?",
                          )
                        ) {
                          removeAppSettings.mutate();
                        }
                      }}
                    >
                      Remover app
                    </button>
                  )}
              </div>
            </form>
          )}
        </section>
      )}
      {accounts.data.can_manage &&
        appSettings.data?.app_secret_configured &&
        !appSettings.data.configured && (
          <ErrorState message="A chave de criptografia do servidor não está configurada. O OWNER deve contatar o suporte antes de conectar contas." />
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
