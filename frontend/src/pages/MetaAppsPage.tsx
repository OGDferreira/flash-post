import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleHelp, Pencil, Plus, Save, Trash2, X } from "lucide-react";

import { ErrorState, LoadingState } from "@/components/PageState";
import { CopyField } from "@/components/ui/CopyField";
import { MetaSetupModal } from "@/features/meta/MetaSetupModal";
import { ApiError, apiRequest } from "@/services/api";
import { confirmAction } from "@/lib/confirm";

type InstagramMetaApp = {
  id: string;
  display_name: string;
  meta_app_name: string;
  app_id: string;
  credential_kind: "legacy" | "instagram_business_login";
  category: string | null;
  app_link: string | null;
  is_selected: boolean;
  app_secret_configured: boolean;
  connected_accounts: number;
};

type InstagramMetaAppsResponse = {
  callback_url: string;
  selected_app_id: string | null;
  apps: InstagramMetaApp[];
};


export function MetaAppsPage() {
  const queryClient = useQueryClient();
  const [displayName, setDisplayName] = useState("");
  const [appId, setAppId] = useState("");
  const [appSecret, setAppSecret] = useState("");
  const [editingAppId, setEditingAppId] = useState<string | null>(null);
  const [editDisplayName, setEditDisplayName] = useState("");
  const [editAppSecret, setEditAppSecret] = useState("");
  const [setupOpen, setSetupOpen] = useState(false);
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

  if (accounts.isLoading) return <LoadingState label="Carregando aplicativos Meta" />;
  if (accounts.error || !accounts.data) {
    return <ErrorState message="Não foi possível carregar as configurações do workspace." />;
  }
  if (!accounts.data.can_manage) {
    return (
      <section className="mx-auto max-w-3xl rounded-xl border border-line bg-surface p-4">
        <h2 className="text-2xl font-semibold text-fg">Aplicativos Meta</h2>
        <p className="mt-3 text-sm leading-6 text-muted">
          Somente o OWNER do workspace pode cadastrar e gerenciar aplicativos Meta.
        </p>
      </section>
    );
  }
  if (metaApps.isLoading) {
    return <LoadingState label="Carregando aplicativos Meta" />;
  }
  if (metaApps.error || !metaApps.data) {
    const message =
      metaApps.error instanceof ApiError
        ? metaApps.error.message
        : "Não foi possível carregar os aplicativos Meta.";
    return <ErrorState message={message} />;
  }

  const mutationError = [
    createMetaApp.error,
    selectMetaApp.error,
    updateMetaApp.error,
    removeMetaApp.error,
  ].find(Boolean);
  const mutationMessage =
    mutationError instanceof ApiError
      ? mutationError.message
      : mutationError
        ? "Não foi possível atualizar as configurações."
        : null;

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <header>
        <p className="text-xs font-medium uppercase tracking-[0.16em] text-accent">Workspace</p>
        <h2 className="mt-2 text-2xl font-semibold tracking-[-0.045em] text-fg sm:text-3xl">
          Apps Meta
        </h2>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">
          Gerencie os aplicativos Meta usados para autorizar novas contas Instagram neste workspace.
        </p>
      </header>

      <section className="space-y-4 rounded-xl border border-line bg-surface p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <h3 className="font-medium text-fg">Aplicativos Meta</h3>
            <p className="mt-2 text-sm leading-6 text-muted">
              Cadastre as credenciais de Instagram Business Login. O segredo é criptografado no
              servidor e nunca é exibido novamente.
            </p>
          </div>
          <button className="btn-secondary shrink-0" onClick={() => setSetupOpen(true)} type="button">
            <CircleHelp size={15} />
            Como configurar
          </button>
        </div>
        {metaApps.data?.callback_url && (
          <CopyField
            hint="Cole exatamente esta URL em Business login settings → OAuth redirect URIs, no painel do seu app na Meta."
            label="URL de callback (OAuth redirect URI)"
            value={metaApps.data.callback_url}
          />
        )}
        <MetaSetupModal callbackUrl={metaApps.data?.callback_url} onClose={() => setSetupOpen(false)} open={setupOpen} />
        {mutationMessage && <ErrorState message={mutationMessage} />}
        <div className="space-y-3">
          {metaApps.data.apps.map((app) => (
            <article
              className={`space-y-4 rounded-lg border p-4 ${
                app.is_selected
                  ? "border-brand bg-brand-soft"
                  : "border-line bg-surface-inset"
              }`}
              key={app.id}
            >
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h4 className="font-medium text-fg">{app.display_name}</h4>
                    {app.is_selected && (
                      <span className="rounded-full bg-[#26366f] px-2 py-0.5 text-xs text-accent">
                        Selecionado
                      </span>
                    )}
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs ${
                        app.connected_accounts
                          ? "bg-success/10 text-success"
                          : "bg-warning/10 text-warning"
                      }`}
                    >
                      {app.connected_accounts === 0
                        ? "Sem contas conectadas"
                        : app.connected_accounts === 1
                          ? "1 conta conectada"
                          : `${app.connected_accounts} contas conectadas`}
                    </span>
                  </div>
                  <p className="mt-1 text-sm text-muted">
                    Instagram App ID: {app.app_id}
                  </p>
                  <p className="mt-1 text-xs text-muted">
                    {app.credential_kind === "legacy"
                      ? "App legado: credenciais e contas vinculadas preservadas."
                      : "Credenciais de Instagram Business Login."}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <button
                    className="grid size-10 place-items-center rounded-lg border border-line text-fg-2 hover:bg-surface-raised"
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
                      className="min-h-10 rounded-lg border border-line px-3 py-2 text-sm text-accent hover:bg-brand-soft disabled:opacity-60"
                      type="button"
                      disabled={selectMetaApp.isPending}
                      onClick={() => selectMetaApp.mutate(app.id)}
                    >
                      Usar para novas conexões
                    </button>
                  )}
                  <button
                    className="grid size-10 place-items-center rounded-lg border border-danger/30 text-danger hover:bg-danger-soft disabled:opacity-60"
                    type="button"
                    aria-label={`Remover ${app.display_name}`}
                    disabled={removeMetaApp.isPending}
                    onClick={async () => {
                      if (
                        await confirmAction(
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
                  className="grid gap-3 border-t border-line pt-4 sm:grid-cols-2"
                  onSubmit={(event) => {
                    event.preventDefault();
                    updateMetaApp.mutate({
                      id: app.id,
                      name: editDisplayName,
                      secret: editAppSecret,
                    });
                  }}
                >
                  <label className="grid gap-2 text-sm text-fg-2">
                    Nome interno
                    <input
                      className="min-h-10 rounded-lg border border-line bg-surface-inset px-3 text-fg outline-none focus:border-brand"
                      maxLength={120}
                      required
                      value={editDisplayName}
                      onChange={(event) => setEditDisplayName(event.target.value)}
                    />
                  </label>
                  <label className="grid gap-2 text-sm text-fg-2">
                    Novo Instagram App Secret (opcional)
                    <input
                      autoComplete="new-password"
                      className="min-h-10 rounded-lg border border-line bg-surface-inset px-3 text-fg outline-none focus:border-brand"
                      maxLength={512}
                      type="password"
                      value={editAppSecret}
                      onChange={(event) => setEditAppSecret(event.target.value)}
                      placeholder="Deixe vazio para manter o atual"
                    />
                  </label>
                  <div className="flex items-center gap-2 sm:col-span-2">
                    <button
                      className="inline-flex min-h-10 items-center gap-2 rounded-lg bg-brand px-3 py-2 text-sm text-white disabled:opacity-60"
                      type="submit"
                      disabled={updateMetaApp.isPending || !editDisplayName.trim()}
                    >
                      <Save size={15} />
                      {updateMetaApp.isPending ? "Salvando..." : "Salvar alterações"}
                    </button>
                    <button
                      className="grid size-10 place-items-center rounded-lg border border-line text-fg-2"
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
            <p className="rounded-lg border border-dashed border-line px-4 py-3 text-sm text-muted">
              Nenhum aplicativo cadastrado. Adicione as credenciais do Instagram Business Login abaixo.
            </p>
          )}
        </div>
        <form
          className="grid gap-4 border-t border-line-soft pt-5 sm:grid-cols-2"
          onSubmit={(event) => {
            event.preventDefault();
            createMetaApp.mutate();
          }}
        >
          <label className="grid gap-2 text-sm text-fg-2 sm:col-span-2">
            Nome para identificar o aplicativo
            <input
              autoComplete="off"
              className="min-h-10 rounded-lg border border-line bg-surface-inset px-3 text-fg outline-none focus:border-brand"
              maxLength={120}
              required
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              placeholder="Ex.: App principal da marca"
            />
          </label>
          <label className="grid gap-2 text-sm text-fg-2">
            Instagram App ID
            <span className="text-xs leading-5 text-muted">
              No painel da Meta, use o Instagram App ID em Instagram → API setup with Instagram
              login → Business login settings. Não use o App ID de Configurações Básicas.
            </span>
            <input
              autoComplete="off"
              className="min-h-10 rounded-lg border border-line bg-surface-inset px-3 text-fg outline-none focus:border-brand"
              inputMode="numeric"
              maxLength={64}
              pattern="[0-9]+"
              required
              value={appId}
              onChange={(event) => setAppId(event.target.value)}
            />
          </label>
          <label className="grid gap-2 text-sm text-fg-2">
            Instagram App Secret
            <span className="text-xs leading-5 text-muted">
              Use o Instagram App Secret na mesma tela Business login settings, não o App Secret
              de Configurações Básicas.
            </span>
            <input
              autoComplete="new-password"
              className="min-h-10 rounded-lg border border-line bg-surface-inset px-3 text-fg outline-none focus:border-brand"
              maxLength={512}
              type="password"
              required
              value={appSecret}
              onChange={(event) => setAppSecret(event.target.value)}
              placeholder="Cole o Instagram App Secret"
            />
          </label>
          <p className="text-xs leading-5 text-muted sm:col-span-2">
            O app Meta deve ser do tipo Business e ter o Instagram Business Login configurado.
            Cadastre o URI de callback exibido pelo FlashPost entre os OAuth redirect URIs nessa
            mesma configuração. O segredo não é retornado nem compartilhado com outros workspaces.
          </p>
          <div className="flex items-center gap-3 sm:col-span-2">
            <button
              className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white transition hover:bg-brand disabled:cursor-not-allowed disabled:opacity-60"
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
    </div>
  );
}
