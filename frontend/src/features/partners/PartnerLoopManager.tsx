import { useState } from "react";
import { Plus, Trash2, RefreshCw } from "lucide-react";
import { useLoopAccounts, useAddAccountToLoop, useRemoveAccountFromLoop } from "@/features/partners/chiefApi";
import type { PartnerLoop, PartnerAccount } from "@/types/chief";
import { LoadingState, ErrorState, EmptyState } from "@/components/PageState";
import { confirmAction } from "@/lib/confirm";

interface PartnerLoopManagerProps {
  workspaceId: string;
  loops: PartnerLoop[];
  accounts: PartnerAccount[];
  isLoading: boolean;
}

export function PartnerLoopManager({ workspaceId, loops, accounts, isLoading }: PartnerLoopManagerProps) {
  const [selectedLoop, setSelectedLoop] = useState<string | null>(null);
  const [showAddAccount, setShowAddAccount] = useState(false);
  const [selectedAccountId, setSelectedAccountId] = useState<string>("");

  const loopAccounts = useLoopAccounts(workspaceId, selectedLoop);
  const addAccount = useAddAccountToLoop();
  const removeAccount = useRemoveAccountFromLoop();

  const selectedLoopData = loops.find(l => l.id === selectedLoop);

  const handleAddAccount = async () => {
    if (!selectedLoop || !selectedAccountId) return;

    await addAccount.mutateAsync({
      workspaceId,
      loopId: selectedLoop,
      accountId: selectedAccountId,
    });

    setShowAddAccount(false);
    setSelectedAccountId("");
  };

  const handleRemoveAccount = async (accountId: string) => {
    if (!selectedLoop) return;

    if (await confirmAction("Remover esta conta do loop?")) {
      await removeAccount.mutateAsync({
        workspaceId,
        loopId: selectedLoop,
        accountId,
      });
    }
  };

  // Filter accounts not in the loop
  const availableAccounts = accounts.filter(
    acc => !loopAccounts.data?.accounts.some(la => la.account_id === acc.id)
  );

  if (isLoading) return <LoadingState label="Carregando loops" />;

  if (loops.length === 0) {
    return <EmptyState message="Nenhum loop criado ainda." />;
  }

  return (
    <div className="space-y-4">
      <div>
        <h4 className="mb-2 text-sm font-semibold text-fg">Selecione um Loop</h4>
        <div className="space-y-2">
          {loops.map((loop) => (
            <button
              key={loop.id}
              className={`w-full rounded-lg border p-3 text-left transition-all ${
                selectedLoop === loop.id
                  ? "border-accent bg-accent/10"
                  : "border-line-soft bg-surface-inset hover:border-accent/50"
              }`}
              onClick={() => setSelectedLoop(loop.id)}
              type="button"
            >
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-fg">{loop.name}</p>
                  <p className="text-xs text-muted">
                    {loop.status === "active" ? "Ativo" : "Pausado"} · {loop.post_type}
                  </p>
                </div>
                {loop.linked && (
                  <span className="rounded-md bg-accent/20 px-2 py-1 text-[10px] font-medium text-accent">
                    Compartilhado
                  </span>
                )}
              </div>
            </button>
          ))}
        </div>
      </div>

      {selectedLoop && selectedLoopData && (
        <div className="rounded-xl border border-line-soft bg-surface-inset p-4">
          <div className="mb-4 flex items-center justify-between">
            <h4 className="flex items-center gap-2 text-sm font-semibold text-fg">
              <RefreshCw size={16} />
              Contas do Loop: {selectedLoopData.name}
            </h4>
            <button
              className="btn-primary btn-sm"
              onClick={() => setShowAddAccount(!showAddAccount)}
              type="button"
            >
              <Plus size={14} />
              Adicionar Conta
            </button>
          </div>

          {showAddAccount && availableAccounts.length > 0 && (
            <div className="mb-4 rounded-lg border border-line-soft bg-surface p-3">
              <div className="flex gap-2">
                <select
                  className="input flex-1"
                  value={selectedAccountId}
                  onChange={(e) => setSelectedAccountId(e.target.value)}
                >
                  <option value="">Selecione uma conta</option>
                  {availableAccounts.map((account) => (
                    <option key={account.id} value={account.id}>
                      @{account.username}
                    </option>
                  ))}
                </select>
                <button
                  className="btn-primary"
                  disabled={!selectedAccountId || addAccount.isPending}
                  onClick={() => void handleAddAccount()}
                  type="button"
                >
                  {addAccount.isPending ? "Adicionando..." : "Adicionar"}
                </button>
              </div>
            </div>
          )}

          {showAddAccount && availableAccounts.length === 0 && (
            <p className="mb-4 rounded-lg border border-line-soft bg-surface p-3 text-sm text-muted">
              Todas as contas já estão no loop.
            </p>
          )}

          {loopAccounts.isLoading && <LoadingState label="Carregando contas do loop" />}
          {loopAccounts.error && (
            <ErrorState message="Erro ao carregar contas." onRetry={() => void loopAccounts.refetch()} />
          )}

          {loopAccounts.data && loopAccounts.data.accounts.length === 0 && (
            <EmptyState message="Nenhuma conta no loop ainda." />
          )}

          {loopAccounts.data && loopAccounts.data.accounts.length > 0 && (
            <div className="space-y-2">
              {loopAccounts.data.accounts.map((loopAccount) => {
                const account = accounts.find(a => a.id === loopAccount.account_id);
                return (
                  <div
                    key={loopAccount.loop_account_id}
                    className="flex items-center justify-between rounded-lg border border-line-soft bg-surface p-3"
                  >
                    <div className="flex items-center gap-3">
                      {account?.profile_picture_url && (
                        <img
                          alt={loopAccount.username}
                          className="h-10 w-10 rounded-full"
                          src={account.profile_picture_url}
                        />
                      )}
                      <div>
                        <p className="text-sm font-medium text-fg">@{loopAccount.username}</p>
                        <p className="text-xs text-muted">
                          Adicionada em {new Date(loopAccount.added_at).toLocaleDateString("pt-BR")}
                        </p>
                      </div>
                    </div>
                    <button
                      className="btn-secondary btn-sm text-danger hover:bg-danger-soft"
                      onClick={() => void handleRemoveAccount(loopAccount.account_id)}
                      type="button"
                      disabled={removeAccount.isPending}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
