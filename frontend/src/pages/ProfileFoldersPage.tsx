import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Folder, Pencil, Plus, Save, Trash2, Users, X } from "lucide-react";

import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { InstagramAvatar } from "@/components/InstagramAvatar";
import {
  formatAccountConnectedAt,
  formatConnectedDuration,
} from "@/features/instagram/accountDates";
import { ApiError, apiRequest } from "@/services/api";

type ProfileFolderAccount = {
  id: string;
  profile_folder_id?: string | null;
  username: string;
  profile_picture_url: string | null;
  status: "connected" | "disconnected" | "error";
  connected_at: string;
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
    setFormOpen(true);
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

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-[#7186ff]">
            Organização
          </p>
          <h2 className="mt-2 flex items-center gap-2 text-2xl font-semibold tracking-[-0.045em] text-[#f5f7fb] sm:text-3xl">
            <Folder size={25} className="text-[#aeb9ce]" />
            Pastas de perfis
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-[#94a3b8]">
            Agrupe contas Instagram por tema ou operação. Cada pasta pode ter uma cor para facilitar
            a identificação dos perfis.
          </p>
        </div>
        <button
          className="inline-flex min-h-10 items-center gap-2 rounded-lg bg-[#00c9d8] px-4 py-2 text-sm font-semibold text-[#062027] hover:bg-[#42dbe5]"
          type="button"
          onClick={openCreateForm}
        >
          <Plus size={16} />
          Nova pasta
        </button>
      </header>

      {mutationError && <ErrorState message={mutationError} />}

      {formOpen && (
        <form
          className="grid gap-4 rounded-xl border border-[#27334a] bg-[#0d1015] p-4 sm:grid-cols-[1fr_auto_auto] sm:items-end"
          onSubmit={(event) => {
            event.preventDefault();
            saveFolder.mutate();
          }}
        >
          <label className="grid gap-2 text-sm text-[#cbd5e1]">
            Nome da pasta
            <input
              className="min-h-10 rounded-lg border border-[#27334a] bg-[#090b0f] px-3 text-[#f5f7fb] outline-none focus:border-[#00c9d8]"
              maxLength={80}
              required
              value={draft.name}
              onChange={(event) => setDraft({ ...draft, name: event.target.value })}
              placeholder="Ex.: Humor, Notícias, Lifestyle"
            />
          </label>
          <label className="flex min-h-10 items-center gap-3 text-sm text-[#cbd5e1]">
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
              className="inline-flex min-h-10 items-center gap-2 rounded-lg bg-[#00c9d8] px-3 text-sm font-semibold text-[#062027] disabled:opacity-60"
              type="submit"
              disabled={saveFolder.isPending || !draft.name.trim()}
            >
              <Save size={15} />
              {saveFolder.isPending ? "Salvando..." : "Salvar"}
            </button>
            <button
              className="grid size-10 place-items-center rounded-lg border border-[#27334a] text-[#94a3b8] hover:text-white"
              type="button"
              onClick={() => setFormOpen(false)}
              aria-label="Cancelar edição da pasta"
            >
              <X size={16} />
            </button>
          </div>
        </form>
      )}

      {folderData.folders.length === 0 ? (
        <EmptyState message="Nenhuma pasta criada. Crie uma pasta e escolha uma cor para começar." />
      ) : (
        <section className="space-y-4" aria-label="Pastas criadas">
          {folderData.folders.map((folder) => (
            <article
              className="space-y-4 rounded-xl border bg-[#0d151c] p-4 sm:p-5"
              key={folder.id}
              style={{ borderColor: `${folder.color}55` }}
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex min-w-0 items-center gap-2">
                  <span className="size-3 shrink-0 rounded-full" style={{ backgroundColor: folder.color }} />
                  <h3 className="truncate font-semibold text-[#f5f7fb]">{folder.name}</h3>
                  <span className="text-xs text-[#94a3b8]">
                    ({folder.accounts.length} {folder.accounts.length === 1 ? "conta" : "contas"})
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    className="grid size-9 place-items-center rounded-lg border border-[#27334a] text-[#aeb9ce] hover:text-white"
                    type="button"
                    aria-label={`Editar pasta ${folder.name}`}
                    onClick={() => openEditForm(folder)}
                  >
                    <Pencil size={15} />
                  </button>
                  <button
                    className="grid size-9 place-items-center rounded-lg border border-[#47252d] text-[#f1a3ad] hover:bg-[#1a1013] disabled:opacity-60"
                    type="button"
                    aria-label={`Excluir pasta ${folder.name}`}
                    disabled={removeFolder.isPending}
                    onClick={() => {
                      if (
                        window.confirm(
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
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                {folder.accounts.map((account) => (
                  <div
                    className="flex min-w-0 items-start gap-2 rounded-lg border bg-[#101923] px-2.5 py-2 text-sm text-[#e6eaf2]"
                    key={account.id}
                    style={{ borderColor: `${folder.color}99` }}
                  >
                    <InstagramAvatar
                      className="size-6 shrink-0 rounded-full border border-[#27334a] object-cover"
                      src={account.profile_picture_url}
                      username={account.username}
                    />
                    <div className="min-w-0">
                      <p className="truncate">@{account.username}</p>
                      <p className="mt-0.5 text-[10px] text-[#94a3b8]">
                        Conectada em {formatAccountConnectedAt(account.connected_at)}
                      </p>
                      {account.status === "error" && (
                        <p className="mt-0.5 text-[10px] text-[#f1a3ad]">
                          Duração antes do erro:{" "}
                          {formatConnectedDuration(account.connected_at, account.error_at)}
                        </p>
                      )}
                    </div>
                  </div>
                ))}
                {folder.accounts.length === 0 && (
                  <p className="text-sm text-[#64748b]">Nenhuma conta nesta pasta ainda.</p>
                )}
              </div>
              <button
                className="inline-flex min-h-9 items-center gap-2 rounded-lg border border-[#27334a] px-3 text-xs font-medium text-[#cbd5e1] hover:bg-[#101923]"
                type="button"
                onClick={() => openAccountManager(folder)}
              >
                <Users size={14} />
                Organizar contas
              </button>
              {managingFolderId === folder.id && (
                <form
                  className="space-y-3 rounded-lg border border-[#27334a] bg-[#090b0f] p-3"
                  onSubmit={(event) => {
                    event.preventDefault();
                    saveFolderAccounts.mutate({
                      folderId: folder.id,
                      accountIds: selectedAccountIds,
                    });
                  }}
                >
                  <p className="text-sm font-medium text-[#f5f7fb]">
                    Selecione as contas que pertencem a {folder.name}
                  </p>
                  <label className="grid gap-1.5 text-xs text-[#94a3b8]">
                    Buscar perfil pelo nome
                    <input
                      className="min-h-9 rounded-lg border border-[#27334a] bg-[#10141b] px-3 text-sm text-[#f5f7fb] outline-none focus:border-[#00c9d8]"
                      type="search"
                      value={accountSearch}
                      onChange={(event) => setAccountSearch(event.target.value)}
                      placeholder="Digite o nome do perfil"
                    />
                  </label>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-xs text-[#94a3b8]">
                      {visibleAccounts.length} {visibleAccounts.length === 1 ? "perfil" : "perfis"}
                      {" "}correspondem à busca
                    </p>
                    <button
                      className="min-h-8 rounded-lg border border-[#27334a] px-3 text-xs font-medium text-[#cbd5e1] hover:bg-[#101923] disabled:opacity-50"
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
                    <p className="py-2 text-xs text-[#94a3b8]">
                      Nenhum perfil corresponde à busca.
                    </p>
                  ) : (
                  <div className="grid max-h-64 gap-2 overflow-y-auto sm:grid-cols-2 lg:grid-cols-3">
                    {visibleAccounts.map((account) => {
                      const checked = selectedAccountIds.includes(account.id);
                      return (
                        <label
                          className={`flex min-h-10 cursor-pointer items-center gap-2 rounded-lg border px-2.5 text-xs ${
                            checked
                              ? "border-[#00c9d8] bg-[#0d3036] text-[#e7fdff]"
                              : "border-[#27334a] bg-[#10141b] text-[#cbd5e1]"
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
                            className="size-6 shrink-0 rounded-full border border-[#27334a] object-cover"
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
                      className="min-h-9 rounded-lg border border-[#27334a] px-3 text-xs text-[#cbd5e1]"
                      type="button"
                      onClick={() => setManagingFolderId(null)}
                    >
                      Cancelar
                    </button>
                    <button
                      className="min-h-9 rounded-lg bg-[#00c9d8] px-3 text-xs font-semibold text-[#062027] disabled:opacity-60"
                      type="submit"
                      disabled={saveFolderAccounts.isPending}
                    >
                      {saveFolderAccounts.isPending ? "Salvando..." : "Salvar contas"}
                    </button>
                  </div>
                </form>
              )}
            </article>
          ))}
        </section>
      )}

      <section className="rounded-xl border border-[#27334a] bg-[#0d1015] p-4">
        <h3 className="font-medium text-[#f5f7fb]">Contas sem pasta ({unassignedCount})</h3>
        <p className="mt-1 text-xs text-[#94a3b8]">
          Contas não atribuídas a nenhuma pasta podem ser movidas pelo botão “Organizar contas”.
        </p>
        {unassignedCount > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {folderData.accounts
              .filter((account) => !account.profile_folder_id)
              .map((account) => (
                <div
                  className="inline-flex items-start gap-2 rounded-lg border border-[#27334a] bg-[#101923] px-2.5 py-1.5 text-xs text-[#cbd5e1]"
                  key={account.id}
                >
                  <InstagramAvatar
                    className="size-6 rounded-full border border-[#27334a] object-cover"
                    src={account.profile_picture_url}
                    username={account.username}
                  />
                  <div>
                    <p>@{account.username}</p>
                    <p className="mt-0.5 text-[10px] text-[#94a3b8]">
                      Conectada em {formatAccountConnectedAt(account.connected_at)}
                    </p>
                    {account.status === "error" && (
                      <p className="mt-0.5 text-[10px] text-[#f1a3ad]">
                        Duração antes do erro:{" "}
                        {formatConnectedDuration(account.connected_at, account.error_at)}
                      </p>
                    )}
                  </div>
                </div>
              ))}
          </div>
        )}
      </section>
    </div>
  );
}
