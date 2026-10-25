import { useState } from "react";
import { Folder, FolderOpen, Plus, RefreshCw, Users } from "lucide-react";
import { useChiefPartners, usePartnerFolders, usePartnerAccounts, usePartnerLoops, useCreatePartnerFolder, useAssignAccountToFolder } from "@/features/partners/chiefApi";
import { LoadingState, ErrorState, EmptyState } from "@/components/PageState";
import { Modal } from "@/components/ui/Modal";
import { PartnerLoopManager } from "./PartnerLoopManager";

export function ChiefPartnerManagement() {
  const [selectedPartner, setSelectedPartner] = useState<string | null>(null);
  const [view, setView] = useState<"folders" | "loops">("folders");
  const [showCreateFolder, setShowCreateFolder] = useState(false);
  const [folderName, setFolderName] = useState("");
  const [folderColor, setFolderColor] = useState("#00c9d8");

  const partners = useChiefPartners();
  const folders = usePartnerFolders(selectedPartner);
  const accounts = usePartnerAccounts(selectedPartner);
  const loops = usePartnerLoops(selectedPartner);
  const createFolder = useCreatePartnerFolder();
  const assignAccount = useAssignAccountToFolder();

  const selectedPartnerData = partners.data?.partners.find(p => p.workspace_id === selectedPartner);

  const handleCreateFolder = async () => {
    if (!selectedPartner || !folderName.trim()) return;

    await createFolder.mutateAsync({
      workspaceId: selectedPartner,
      data: { name: folderName, color: folderColor },
    });

    setShowCreateFolder(false);
    setFolderName("");
    setFolderColor("#00c9d8");
  };

  const handleAssignToFolder = async (accountId: string, folderId: string | null) => {
    if (!selectedPartner) return;

    await assignAccount.mutateAsync({
      workspaceId: selectedPartner,
      accountId,
      folderId,
    });
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-2xl font-semibold text-fg">
          <Users className="text-accent" size={24} />
          Gerenciar Sócios
        </h2>
      </div>

      {partners.isLoading && <LoadingState label="Carregando sócios" />}
      {partners.error && <ErrorState message="Não foi possível carregar os sócios." onRetry={() => void partners.refetch()} />}

      {partners.data && partners.data.partners.length === 0 && (
        <EmptyState message="Você não possui sócios ativos no momento." />
      )}

      {partners.data && partners.data.partners.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {partners.data.partners.map((partner) => (
            <button
              key={partner.workspace_id}
              className={`rounded-xl border p-4 text-left transition-all ${
                selectedPartner === partner.workspace_id
                  ? "border-accent bg-accent/10 shadow-lg"
                  : "border-line-soft bg-surface hover:border-accent/50 hover:bg-surface-hover"
              }`}
              onClick={() => setSelectedPartner(partner.workspace_id)}
              type="button"
            >
              <p className="font-semibold text-fg">{partner.user_name}</p>
              <p className="mt-1 text-xs text-muted">{partner.user_email}</p>
              <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted">
                <span>{partner.account_count} contas</span>
                <span>·</span>
                <span>{partner.folder_count} pastas</span>
                <span>·</span>
                <span>{partner.loop_count} loops</span>
              </div>
            </button>
          ))}
        </div>
      )}

      {selectedPartner && selectedPartnerData && (
        <div className="rounded-xl border border-line-soft bg-surface p-4">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-lg font-semibold text-fg">
              Gerenciando: {selectedPartnerData.user_name}
            </h3>
            <div className="flex gap-2">
              <button
                className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
                  view === "folders"
                    ? "bg-accent text-white"
                    : "bg-surface-inset text-muted hover:bg-surface-hover"
                }`}
                onClick={() => setView("folders")}
                type="button"
              >
                <Folder size={16} className="inline mr-1" />
                Pastas
              </button>
              <button
                className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
                  view === "loops"
                    ? "bg-accent text-white"
                    : "bg-surface-inset text-muted hover:bg-surface-hover"
                }`}
                onClick={() => setView("loops")}
                type="button"
              >
                <RefreshCw size={16} className="inline mr-1" />
                Loops
              </button>
            </div>
          </div>

          {view === "folders" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h4 className="text-sm font-semibold text-fg">Pastas de Perfis</h4>
                <button
                  className="btn-primary btn-sm"
                  onClick={() => setShowCreateFolder(true)}
                  type="button"
                >
                  <Plus size={14} />
                  Nova Pasta
                </button>
              </div>

              {folders.isLoading && <LoadingState label="Carregando pastas" />}
              {folders.error && <ErrorState message="Erro ao carregar pastas." onRetry={() => void folders.refetch()} />}

              {folders.data && folders.data.folders.length === 0 && (
                <EmptyState message="Nenhuma pasta criada ainda." />
              )}

              {folders.data && folders.data.folders.length > 0 && (
                <div className="space-y-2">
                  {folders.data.folders.map((folder) => (
                    <div
                      key={folder.id}
                      className="flex items-center gap-3 rounded-lg border border-line-soft bg-surface-inset p-3"
                    >
                      <FolderOpen size={20} style={{ color: folder.color }} />
                      <div className="flex-1">
                        <p className="text-sm font-medium text-fg">{folder.name}</p>
                        {folder.auto_prefixes.length > 0 && (
                          <p className="text-xs text-muted">
                            Auto: {folder.auto_prefixes.join(", ")}
                          </p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              <div className="mt-4">
                <h4 className="mb-2 text-sm font-semibold text-fg">Contas do Sócio</h4>
                {accounts.isLoading && <LoadingState label="Carregando contas" />}
                {accounts.error && <ErrorState message="Erro ao carregar contas." onRetry={() => void accounts.refetch()} />}

                {accounts.data && accounts.data.accounts.length === 0 && (
                  <EmptyState message="Nenhuma conta conectada." />
                )}

                {accounts.data && accounts.data.accounts.length > 0 && (
                  <div className="space-y-2">
                    {accounts.data.accounts.map((account) => (
                      <div
                        key={account.id}
                        className="flex items-center justify-between rounded-lg border border-line-soft bg-surface-inset p-3"
                      >
                        <div className="flex items-center gap-3">
                          {account.profile_picture_url && (
                            <img
                              alt={account.username}
                              className="h-10 w-10 rounded-full"
                              src={account.profile_picture_url}
                            />
                          )}
                          <div>
                            <p className="text-sm font-medium text-fg">@{account.username}</p>
                            <p className="text-xs text-muted">
                              {account.follower_count?.toLocaleString() || "?"} seguidores
                            </p>
                          </div>
                        </div>
                        <select
                          className="input-sm"
                          value={account.folder_id || ""}
                          onChange={(e) => void handleAssignToFolder(account.id, e.target.value || null)}
                        >
                          <option value="">Sem pasta</option>
                          {folders.data?.folders.map((folder) => (
                            <option key={folder.id} value={folder.id}>
                              {folder.name}
                            </option>
                          ))}
                        </select>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {view === "loops" && (
            <PartnerLoopManager
              workspaceId={selectedPartner}
              loops={loops.data?.loops || []}
              accounts={accounts.data?.accounts || []}
              isLoading={loops.isLoading || accounts.isLoading}
            />
          )}
        </div>
      )}

      {showCreateFolder && (
        <Modal onClose={() => setShowCreateFolder(false)} open title="Nova Pasta">
          <div className="space-y-4">
            <div>
              <label className="mb-2 block text-sm font-medium text-fg" htmlFor="folder-name">
                Nome da Pasta
              </label>
              <input
                id="folder-name"
                className="input w-full"
                placeholder="Ex: Contas Principais"
                type="text"
                value={folderName}
                onChange={(e) => setFolderName(e.target.value)}
              />
            </div>
            <div>
              <label className="mb-2 block text-sm font-medium text-fg" htmlFor="folder-color">
                Cor
              </label>
              <input
                id="folder-color"
                className="h-10 w-full rounded-lg"
                type="color"
                value={folderColor}
                onChange={(e) => setFolderColor(e.target.value)}
              />
            </div>
            <div className="flex justify-end gap-2 border-t border-line-soft pt-4">
              <button className="btn-secondary" onClick={() => setShowCreateFolder(false)} type="button">
                Cancelar
              </button>
              <button
                className="btn-primary"
                disabled={!folderName.trim() || createFolder.isPending}
                onClick={() => void handleCreateFolder()}
                type="button"
              >
                {createFolder.isPending ? "Criando..." : "Criar Pasta"}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
