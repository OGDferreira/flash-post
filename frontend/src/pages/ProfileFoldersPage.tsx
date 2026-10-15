import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Folder, Pencil, Plus, Save, Trash2, Users, X } from "lucide-react";

import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { InstagramAvatar } from "@/components/InstagramAvatar";
import { Modal } from "@/components/ui/Modal";
import {
  formatAccountConnectedAt,
  formatConnectedDuration,
} from "@/features/instagram/accountDates";
import { ApiError, apiRequest } from "@/services/api";
import { confirmAction } from "@/lib/confirm";

type ProfileFolderAccount = {
  id: string;
  profile_folder_id?: string | null;
  username: string;
  profile_picture_url: string | null;
  status: "connected" | "disconnected" | "error";
  connected_at: string;
  connected_by_name?: string | null;
  error_at: string | null;
};

type ProfileFolder = {
  id: string;
  name: string;
  color: string;
  created_at: string;
  accounts: ProfileFolderAccount[];
};

type ProfileFoldersResponse = {
  folders: ProfileFolder[];
  accounts: ProfileFolderAccount[];
};

const emptyDraft = { name: "", color: "#00c9d8" };

function getErrorMessage(error: unknown, fallback: string): string | null {
  if (!error) return null;
  return error instanceof ApiError ? error.message : fallback;
}

export function ProfileFoldersPage() {
  const queryClient = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState(emptyDraft);
  const [managingFolderId, setManagingFolderId] = useState<string | null>(null);
  const [selectedAccountIds, setSelectedAccountIds] = useState<string[]>([]);
  const [accountSearch, setAccountSearch] = useState("");
  const [assigningAccount, setAssigningAccount] = useState<ProfileFolderAccount | null>(null);
  const folders = useQuery({
    queryKey: ["instagram", "folders"],
    queryFn: () => apiRequest<ProfileFoldersResponse>("/api/instagram/folders"),
    retry: false,
  });
  const saveFolder = useMutation({
    mutationFn: () =>
      apiRequest<ProfileFolder>(
        editingId ? `/api/instagram/folders/${editingId}` : "/api/instagram/folders",
        {
          method: editingId ? "PATCH" : "POST",
          body: draft,
        },
      ),
    onSuccess: () => {
      setFormOpen(false);
      setEditingId(null);
      setDraft(emptyDraft);
      void queryClient.invalidateQueries({ queryKey: ["instagram", "folders"] });
    },
  });
  const removeFolder = useMutation({
    mutationFn: (id: string) =>
      apiRequest(`/api/instagram/folders/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["instagram", "folders"] });
      void queryClient.invalidateQueries({ queryKey: ["instagram", "accounts"] });
    },
  });
  const saveFolderAccounts = useMutation({
    mutationFn: ({ folderId, accountIds }: { folderId: string; accountIds: string[] }) =>
      apiRequest<ProfileFolder>(`/api/instagram/folders/${folderId}/accounts`, {
        method: "PUT",
        body: { account_ids: accountIds },
      }),
    onSuccess: () => {
      setManagingFolderId(null);
      setAssigningAccount(null);
      setSelectedAccountIds([]);
      void queryClient.invalidateQueries({ queryKey: ["instagram", "folders"] });
      void queryClient.invalidateQueries({ queryKey: ["instagram", "accounts"] });
    },
  });

  if (folders.isLoading) return <LoadingState label="Carregando pastas de perfis" />;
  if (folders.error || !folders.data) {
    return <ErrorState message="Não foi possível carregar as pastas de perfis." />;
  }

  const folderData = folders.data;
  const mutationError =
    getErrorMessage(saveFolder.error, "Não foi possível salvar a pasta.") ??
    getErrorMessage(removeFolder.error, "Não foi possível remover a pasta.") ??
    getErrorMessage(saveFolderAccounts.error, "Não foi possível organizar as contas.");
  const folderAccountIds = folderData.accounts
    .filter((account) => account.profile_folder_id)
    .map((account) => account.id);
  const unassignedCount = folderData.accounts.length - folderAccountIds.length;
  const query = accountSearch.trim().toLocaleLowerCase("pt-BR");
  const visibleAccounts = folderData.accounts.filter((account) =>
    account.username.toLocaleLowerCase("pt-BR").includes(query),
  );

  function openCreateForm() {
    setEditingId(null);
    setDraft(emptyDraft);
    setFormOpen(true);
    saveFolder.reset();
  }

  function openEditForm(folder: ProfileFolder) {
    setEditingId(folder.id);
    setDraft({ name: folder.name, color: folder.color });
    setFormOpen(false);
    saveFolder.reset();
  }

  function openAccountManager(folder: ProfileFolder) {
    setManagingFolderId(folder.id);
    setAccountSearch("");
    setSelectedAccountIds(
      folderData.accounts
        .filter((account) => account.profile_folder_id === folder.id)
        .map((account) => account.id),
    );
    saveFolderAccounts.reset();
  }

  const managingFolder = folderData.folders.find((folder) => folder.id === managingFolderId) ?? null;

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-accent">
            Organização
          </p>
          <h2 className="mt-2 flex items-center gap-2 text-2xl font-semibold tracking-[-0.045em] text-fg sm:text-3xl">
            <Folder size={25} className="text-fg-2" />
            Pastas de perfis
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">
            Agrupe contas Instagram por tema ou operação. Cada pasta pode ter uma cor para facilitar
            a identificação dos perfis.
          </p>
        </div>
        <button
          className="inline-flex min-h-10 items-center gap-2 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-strong"
          type="button"
          onClick={openCreateForm}
        >
          <Plus size={16} />
          Nova pasta
        </button>
      </header>

      {mutationError && <ErrorState message={mutationError} />}

      {formOpen && !editingId && (
        <form
          className="grid gap-4 rounded-xl border border-line bg-surface p-4 sm:grid-cols-[1fr_auto_auto] sm:items-end"
          onSubmit={(event) => {
            event.preventDefault();
            saveFolder.mutate();
          }}
        >
          <label className="grid gap-2 text-sm text-fg-2">
            Nome da pasta
            <input
              className="min-h-10 rounded-lg border border-line bg-surface-inset px-3 text-fg outline-none focus:border-brand"
              maxLength={80}
              required
              value={draft.name}
              onChange={(event) => setDraft({ ...draft, name: event.target.value })}
              placeholder="Ex.: Humor, Notícias, Lifestyle"
            />
          </label>
          <label className="flex min-h-10 items-center gap-3 text-sm text-fg-2">
            Cor da pasta
            <input
              className="size-10 cursor-pointer rounded border-0 bg-transparent p-0"
              type="color"
              value={draft.color}
              onChange={(event) => setDraft({ ...draft, color: event.target.value })}
              aria-label="Escolher cor da pasta"
            />
          </label>
          <div className="flex gap-2">
            <button
              className="inline-flex min-h-10 items-center gap-2 rounded-lg bg-brand px-3 text-sm font-semibold text-white disabled:opacity-60"
              type="submit"
              disabled={saveFolder.isPending || !draft.name.trim()}
            >
              <Save size={15} />
              {saveFolder.isPending ? "Salvando..." : "Salvar"}
            </button>
            <button
              className="grid size-10 place-items-center rounded-lg border border-line text-muted hover:text-white"
              type="button"
              onClick={() => setFormOpen(false)}
              aria-label="Cancelar edição da pasta"
            >
              <X size={16} />
            </button>
          </div>
        </form>
      )}

      <section className="rounded-xl border border-line bg-surface p-4">
        <h3 className="font-medium text-fg">Contas sem pasta ({unassignedCount})</h3>
        <p className="mt-1 text-xs text-muted">
          Toque em uma conta para escolher a pasta dela, ou use “Organizar contas” em uma pasta.
        </p>
        {unassignedCount > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {folderData.accounts
              .filter((account) => !account.profile_folder_id)
              .map((account) => (
                <button
                  className="inline-flex items-start gap-2 rounded-xl border border-line bg-surface px-3 py-2 text-left text-xs text-fg-2 transition-shadow active:shadow-none"
                  key={account.id}
                  onClick={() => {
                    saveFolderAccounts.reset();
                    setAssigningAccount(account);
                  }}
                  type="button"
                >
                  <InstagramAvatar
                    className="size-6 rounded-full border border-line object-cover"
                    src={account.profile_picture_url}
                    username={account.username}
                  />
                  <div>
                    <p>@{account.username}</p>
                    <p className="mt-0.5 text-[10px] text-muted">
                      Conectada em {formatAccountConnectedAt(account.connected_at)}
                      {account.connected_by_name ? ` · por ${account.connected_by_name}` : ""}
                    </p>
                    {account.status === "error" && (
                      <p className="mt-0.5 text-[10px] text-danger">
                        Duração antes do erro:{" "}
                        {formatConnectedDuration(account.connected_at, account.error_at)}
                      </p>
                    )}
                  </div>
                </button>
              ))}
          </div>
        )}
      </section>

      {folderData.folders.length === 0 ? (
        <EmptyState message="Nenhuma pasta criada. Crie uma pasta e escolha uma cor para começar." />
      ) : (
        <section className="grid items-start gap-4 lg:grid-cols-2" aria-label="Pastas criadas">
          {folderData.folders.map((folder) => (
            <article
              className="space-y-4 rounded-xl border bg-well p-4 sm:p-4"
              key={folder.id}
              style={{ borderColor: `${folder.color}55` }}
            >
              {editingId === folder.id ? (
                <form
                  className="flex flex-wrap items-center gap-2"
                  onSubmit={(event) => {
                    event.preventDefault();
                    saveFolder.mutate();
                  }}
                >
                  <input
                    aria-label="Nome da pasta"
                    autoFocus
                    className="field min-h-10 min-w-0 flex-1"
                    maxLength={80}
                    onChange={(event) => setDraft({ ...draft, name: event.target.value })}
                    onKeyDown={(event) => event.key === "Escape" && setEditingId(null)}
                    required
                    value={draft.name}
                  />
                  <input
                    aria-label="Escolher cor da pasta"
                    className="size-10 shrink-0 cursor-pointer rounded border-0 bg-transparent p-0"
                    onChange={(event) => setDraft({ ...draft, color: event.target.value })}
                    type="color"
                    value={draft.color}
                  />
                  <button className="btn-primary btn-sm" disabled={saveFolder.isPending || !draft.name.trim()} type="submit">
                    <Save size={14} />
                    {saveFolder.isPending ? "Salvando..." : "Salvar"}
                  </button>
                  <button aria-label="Cancelar edição da pasta" className="btn-ghost btn-sm" onClick={() => setEditingId(null)} type="button">
                    <X size={15} />
                  </button>
                </form>
              ) : (
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex min-w-0 items-center gap-2">
                  <span className="size-3 shrink-0 rounded-full" style={{ backgroundColor: folder.color }} />
                  <h3 className="truncate font-semibold text-fg">{folder.name}</h3>
                  <span className="text-xs text-muted">
                    ({folder.accounts.length} {folder.accounts.length === 1 ? "conta" : "contas"})
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-line px-2.5 text-xs font-medium text-fg-2 hover:text-white"
                    type="button"
                    onClick={() => openAccountManager(folder)}
                  >
                    <Users size={14} />
                    Organizar contas
                  </button>
                  <button
                    className="grid size-9 place-items-center rounded-lg border border-line text-fg-2 hover:text-white"
                    type="button"
                    aria-label={`Editar pasta ${folder.name}`}
                    onClick={() => openEditForm(folder)}
                  >
                    <Pencil size={15} />
                  </button>
                  <button
                    className="grid size-9 place-items-center rounded-lg border border-danger/30 text-danger hover:bg-danger-soft disabled:opacity-60"
                    type="button"
                    aria-label={`Excluir pasta ${folder.name}`}
                    disabled={removeFolder.isPending}
                    onClick={async () => {
                      if (
                        await confirmAction(
                          `Excluir a pasta "${folder.name}"? As contas serão mantidas e ficarão sem pasta.`,
                        )
                      ) {
                        removeFolder.mutate(folder.id);
                      }
                    }}
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              </div>
              )}
              <div className="grid gap-2 sm:grid-cols-2">
                {folder.accounts.map((account) => (
                  <div
                    className="flex min-w-0 items-start gap-2 rounded-lg border bg-well px-2.5 py-2 text-sm text-fg"
                    key={account.id}
                    style={{ borderColor: `${folder.color}99` }}
                  >
                    <InstagramAvatar
                      className="size-6 shrink-0 rounded-full border border-line object-cover"
                      src={account.profile_picture_url}
                      username={account.username}
                    />
                    <div className="min-w-0">
                      <p className="truncate">@{account.username}</p>
                      <p className="mt-0.5 text-[10px] text-muted">
                        Conectada em {formatAccountConnectedAt(account.connected_at)}
                      {account.connected_by_name ? ` · por ${account.connected_by_name}` : ""}
                      </p>
                      {account.status === "error" && (
                        <p className="mt-0.5 text-[10px] text-danger">
                          Duração antes do erro:{" "}
                          {formatConnectedDuration(account.connected_at, account.error_at)}
                        </p>
                      )}
                    </div>
                  </div>
                ))}
                {folder.accounts.length === 0 && (
                  <p className="text-sm text-muted">Nenhuma conta nesta pasta ainda.</p>
                )}
              </div>
            </article>
          ))}
        </section>
      )}

      <Modal
        busy={saveFolderAccounts.isPending}
        description="Selecione as contas que pertencem a esta pasta."
        onClose={() => setManagingFolderId(null)}
        open={Boolean(managingFolder)}
        title={managingFolder ? `Organizar contas · ${managingFolder.name}` : "Organizar contas"}
        wide
      >
        {managingFolder && (
<form
                  className="space-y-3"
                  onSubmit={(event) => {
                    event.preventDefault();
                    saveFolderAccounts.mutate({
                      folderId: managingFolder.id,
                      accountIds: selectedAccountIds,
                    });
                  }}
                >
                  <label className="grid gap-1.5 text-xs text-muted">
                    Buscar perfil pelo nome
                    <input
                      className="min-h-9 rounded-lg border border-line bg-surface-raised px-3 text-sm text-fg outline-none focus:border-brand"
                      type="search"
                      value={accountSearch}
                      onChange={(event) => setAccountSearch(event.target.value)}
                      placeholder="Digite o nome do perfil"
                    />
                  </label>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-xs text-muted">
                      {visibleAccounts.length} {visibleAccounts.length === 1 ? "perfil" : "perfis"}
                      {" "}correspondem à busca
                    </p>
                    <button
                      className="min-h-8 rounded-lg border border-line px-3 text-xs font-medium text-fg-2 hover:bg-well disabled:opacity-50"
                      type="button"
                      disabled={visibleAccounts.length === 0}
                      onClick={() =>
                        setSelectedAccountIds((current) =>
                          Array.from(
                            new Set([...current, ...visibleAccounts.map((account) => account.id)]),
                          ),
                        )
                      }
                    >
                      Selecionar todos
                    </button>
                  </div>
                  {visibleAccounts.length === 0 ? (
                    <p className="py-2 text-xs text-muted">
                      Nenhum perfil corresponde à busca.
                    </p>
                  ) : (
                  <div className="grid max-h-[50vh] gap-2 overflow-y-auto sm:grid-cols-2">
                    {visibleAccounts.map((account) => {
                      const checked = selectedAccountIds.includes(account.id);
                      return (
                        <label
                          className={`flex min-h-10 cursor-pointer items-center gap-2 rounded-lg border px-2.5 text-xs ${
                            checked
                              ? "border-brand bg-brand-soft text-fg"
                              : "border-line bg-surface-raised text-fg-2"
                          }`}
                          key={account.id}
                        >
                          <input
                            className="accent-[#00c9d8]"
                            type="checkbox"
                            checked={checked}
                            onChange={() =>
                              setSelectedAccountIds((current) =>
                                checked
                                  ? current.filter((id) => id !== account.id)
                                  : [...current, account.id],
                              )
                            }
                          />
                          <InstagramAvatar
                            className="size-6 shrink-0 rounded-full border border-line object-cover"
                            src={account.profile_picture_url}
                            username={account.username}
                          />
                          <span className="truncate">@{account.username}</span>
                        </label>
                      );
                    })}
                  </div>
                  )}
                  <div className="flex justify-end gap-2">
                    <button
                      className="min-h-9 rounded-lg border border-line px-3 text-xs text-fg-2"
                      type="button"
                      onClick={() => setManagingFolderId(null)}
                    >
                      Cancelar
                    </button>
                    <button
                      className="min-h-9 rounded-lg bg-brand px-3 text-xs font-semibold text-white disabled:opacity-60"
                      type="submit"
                      disabled={saveFolderAccounts.isPending}
                    >
                      {saveFolderAccounts.isPending ? "Salvando..." : "Salvar contas"}
                    </button>
                  </div>
                </form>
        )}
      </Modal>

      <Modal
        busy={saveFolderAccounts.isPending}
        description="Escolha a pasta para esta conta."
        onClose={() => setAssigningAccount(null)}
        open={Boolean(assigningAccount)}
        title={assigningAccount ? `Mover @${assigningAccount.username}` : "Mover conta"}
      >
        {folderData.folders.length === 0 ? (
          <p className="text-sm text-muted">Crie uma pasta primeiro.</p>
        ) : (
          <ul className="space-y-2.5">
            {folderData.folders.map((folder) => (
              <li key={folder.id}>
                <button
                  className="flex w-full items-center gap-3 rounded-2xl border border-line bg-surface p-3.5 text-left text-sm text-fg disabled:opacity-60"
                  disabled={saveFolderAccounts.isPending}
                  onClick={() =>
                    assigningAccount &&
                    saveFolderAccounts.mutate({
                      folderId: folder.id,
                      accountIds: [...folder.accounts.map((item) => item.id), assigningAccount.id],
                    })
                  }
                  type="button"
                >
                  <span className="size-3 shrink-0 rounded-full" style={{ backgroundColor: folder.color }} />
                  <span className="min-w-0 flex-1 truncate font-medium">{folder.name}</span>
                  <span className="text-xs text-muted">{folder.accounts.length}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {saveFolderAccounts.error && (
          <p className="mt-3 text-sm text-danger" role="alert">
            {getErrorMessage(saveFolderAccounts.error, "Não foi possível mover a conta.")}
          </p>
        )}
      </Modal>
    </div>
  );
}
