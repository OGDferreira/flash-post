import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Pencil, Plus, Save, Trash2, X } from "lucide-react";

import { ErrorState, LoadingState } from "@/components/PageState";
import { ApiError, apiRequest } from "@/services/api";

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
  selected_app_id: string | null;
  apps: InstagramMetaApp[];
};

type SharkbotWebhookSettings = {
  webhook_url: string;
};

export function SettingsPage() {
  const queryClient = useQueryClient();
  const [displayName, setDisplayName] = useState("");
  const [appId, setAppId] = useState("");
  const [appSecret, setAppSecret] = useState("");
  const [editingAppId, setEditingAppId] = useState<string | null>(null);
  const [editDisplayName, setEditDisplayName] = useState("");
  const [editAppSecret, setEditAppSecret] = useState("");
  const [copyFeedback, setCopyFeedback] = useState<string | null>(null);
  const accounts = useQuery({
    queryKey: ["instagram", "accounts"],
    queryFn: () => apiRequest<{ can_manage: boolean }>("/api/instagram/accounts"),
    retry: false,
  });
  const metaApps = useQuery({
    queryKey: ["instagram", "apps"],
    queryFn: () => apiRequest<InstagramMetaAppsResponse>("/api/instagram/apps"),
    enabled: accounts.data?.can_manage === true,
    retry: false,
  });
  const sharkbotSettings = useQuery({
    queryKey: ["sharkbot", "webhook-settings"],
    queryFn: () => apiRequest<SharkbotWebhookSettings>("/api/sharkbot/webhook/config"),
    enabled: accounts.data?.can_manage === true,
    retry: false,
  });
  const invalidateApps = () => {
    void queryClient.invalidateQueries({ queryKey: ["instagram", "apps"] });
  };
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
      invalidateApps();
    },
  });
  const selectMetaApp = useMutation({
    mutationFn: (id: string) => apiRequest(`/api/instagram/apps/${id}/select`, { method: "PUT" }),
    onSuccess: invalidateApps,
  });
  const updateMetaApp = useMutation({
    mutationFn: ({ id, name, secret }: { id: string; name: string; secret: string }) =>
      apiRequest(`/api/instagram/apps/${id}`, {
        method: "PATCH",
        body: { display_name: name, ...(secret.trim() ? { app_secret: secret } : {}) },
      }),
    onSuccess: () => {
      setEditingAppId(null);
      setEditDisplayName("");
      setEditAppSecret("");
      invalidateApps();
    },
  });
  const removeMetaApp = useMutation({
    mutationFn: (id: string) => apiRequest(`/api/instagram/apps/${id}`, { method: "DELETE" }),
    onSuccess: invalidateApps,
  });
  const rotateSharkbotWebhook = useMutation({
    mutationFn: () =>
      apiRequest<SharkbotWebhookSettings>("/api/sharkbot/webhook/rotate", {
        method: "POST",
      }),
    onSuccess: (settings) => {
      queryClient.setQueryData(["sharkbot", "webhook-settings"], settings);
      setCopyFeedback("URL renovada. Atualize o endereço configurado no Sharkbot.");
    },
  });

  if (accounts.isLoading) return <LoadingState label="Carregando configurações" />;
  if (accounts.error || !accounts.data) {
    return <ErrorState message="Não foi possível carregar as configurações do workspace." />;
  }
  if (!accounts.data.can_manage) {
    return (
      <section className="mx-auto max-w-3xl rounded-xl border border-[#27334a] bg-[#0d1015] p-6">
        <h2 className="text-2xl font-semibold text-[#f5f7fb]">Configurações</h2>
        <p className="mt-3 text-sm leading-6 text-[#94a3b8]">
          Somente o OWNER do workspace pode cadastrar e gerenciar aplicativos Meta.
        </p>
      </section>
    );
  }
  if (metaApps.isLoading || sharkbotSettings.isLoading) {
    return <LoadingState label="Carregando configurações" />;
  }
  if (metaApps.error || !metaApps.data) {
    const message =
      metaApps.error instanceof ApiError
        ? metaApps.error.message
        : "Não foi possível carregar os aplicativos Meta.";
    return <ErrorState message={message} />;
  }
  if (sharkbotSettings.error || !sharkbotSettings.data) {
    const message =
      sharkbotSettings.error instanceof ApiError
        ? sharkbotSettings.error.message
        : "Não foi possível carregar a URL do webhook Sharkbot.";
    return <ErrorState message={message} />;
  }

  const mutationError = [
    createMetaApp.error,
    selectMetaApp.error,
    updateMetaApp.error,
    removeMetaApp.error,
    rotateSharkbotWebhook.error,
  ].find(Boolean);
  const mutationMessage =
    mutationError instanceof ApiError
      ? mutationError.message
      : mutationError
        ? "Não foi possível atualizar as configurações."
        : null;

  return (
    <div className="mx-auto max-w-4xl space-y-7">
      <header>
        <p className="text-xs font-medium uppercase tracking-[0.16em] text-[#7186ff]">Workspace</p>
        <h2 className="mt-2 text-2xl font-semibold tracking-[-0.045em] text-[#f5f7fb] sm:text-3xl">
          Configurações
        </h2>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-[#94a3b8]">
          Gerencie os aplicativos Meta usados para autorizar novas contas Instagram neste workspace.
        </p>
      </header>

      <section className="space-y-5 rounded-xl border border-[#27334a] bg-[#0d1015] p-5 sm:p-6">
        <div>
          <h3 className="font-medium text-[#f5f7fb]">Aplicativos Meta</h3>
          <p className="mt-2 text-sm leading-6 text-[#94a3b8]">
            O segredo é validado na Meta e criptografado no servidor; nunca é exibido novamente.
          </p>
        </div>
        {mutationMessage && <ErrorState message={mutationMessage} />}
        <div className="space-y-3">
          {metaApps.data.apps.map((app) => (
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
          {metaApps.data.apps.length === 0 && (
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
            App ID
            <span className="text-xs leading-5 text-[#94a3b8]">
              Use o App ID de Configurações Básicas no painel da Meta. Não use o ID da API do
              Instagram.
            </span>
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
            App Secret
            <span className="text-xs leading-5 text-[#94a3b8]">
              Use o App Secret de Configurações Básicas do mesmo aplicativo Meta acima, não uma
              chave/ID da API do Instagram.
            </span>
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
            Ao cadastrar, o FlashPost consulta o nome e as informações públicas disponíveis na Meta.
            O segredo não será retornado nem compartilhado com outros workspaces.
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
      </section>
      <section className="space-y-4 rounded-xl border border-[#27334a] bg-[#0d1015] p-5 sm:p-6">
        <div>
          <h3 className="font-medium text-[#f5f7fb]">Integração Sharkbot</h3>
          <p className="mt-2 text-sm leading-6 text-[#94a3b8]">
            Copie esta URL individual e cadastre-a como destino de webhook no Sharkbot. Os eventos
            recebidos serão associados apenas a este workspace.
          </p>
        </div>
        <label className="grid gap-2 text-sm text-[#cbd5e1]">
          URL do webhook para cadastrar no Sharkbot
          <input
            className="min-h-11 rounded-lg border border-[#27334a] bg-[#090b0f] px-3 font-mono text-xs text-[#cbd5e1] outline-none focus:border-[#7186ff]"
            readOnly
            value={sharkbotSettings.data.webhook_url}
          />
        </label>
        {copyFeedback && (
          <p className="text-sm text-[#9de0c0]" role="status">
            {copyFeedback}
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          <button
            className="inline-flex min-h-10 items-center gap-2 rounded-lg bg-[#536dfe] px-3 py-2 text-sm text-white disabled:opacity-60"
            type="button"
            onClick={() => {
              void navigator.clipboard
                .writeText(sharkbotSettings.data.webhook_url)
                .then(() => setCopyFeedback("URL copiada. Cole-a nas configurações do Sharkbot."))
                .catch(() =>
                  setCopyFeedback("Não foi possível copiar automaticamente. Selecione e copie a URL."),
                );
            }}
          >
            <Copy size={15} />
            Copiar URL
          </button>
          <button
            className="min-h-10 rounded-lg border border-[#47252d] px-3 py-2 text-sm text-[#f1a3ad] disabled:opacity-60"
            type="button"
            disabled={rotateSharkbotWebhook.isPending}
            onClick={() => {
              if (
                window.confirm(
                  "Gerar uma nova URL invalidará imediatamente a URL atual. Será necessário atualizá-la no Sharkbot. Continuar?",
                )
              ) {
                rotateSharkbotWebhook.mutate();
              }
            }}
          >
            {rotateSharkbotWebhook.isPending ? "Gerando..." : "Gerar nova URL"}
          </button>
        </div>
      </section>
    </div>
  );
}
