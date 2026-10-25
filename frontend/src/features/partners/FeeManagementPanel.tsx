import { useState } from "react";
import { ArrowRightLeft, DollarSign, History, Users } from "lucide-react";
import { useCurrentFees, useUpdateUserFee, useUpdateGlobalFee, useFeeHistory, usePreviewGlobalFeeChange, brlFee } from "@/features/partners/feesApi";
import { LoadingState, ErrorState } from "@/components/PageState";
import { Modal } from "@/components/ui/Modal";
import { confirmAction } from "@/lib/confirm";

export function FeeManagementPanel() {
  const [selectedUser, setSelectedUser] = useState<string | null>(null);
  const [newFee, setNewFee] = useState<string>("");
  const [reason, setReason] = useState("");
  const [showHistory, setShowHistory] = useState(false);
  const [showGlobalPreview, setShowGlobalPreview] = useState(false);

  const currentFees = useCurrentFees();
  const updateUserFee = useUpdateUserFee();
  const updateGlobalFee = useUpdateGlobalFee();
  const feeHistory = useFeeHistory();
  const previewGlobal = usePreviewGlobalFeeChange();

  const handleUpdateUserFee = async () => {
    if (!selectedUser) return;

    const feeValue = newFee === "" ? null : parseFloat(newFee);

    if (await confirmAction(`Alterar taxa de ${selectedUser} para ${brlFee(feeValue)}?`)) {
      await updateUserFee.mutateAsync({
        user_id: selectedUser,
        new_fee: feeValue,
        reason: reason || undefined,
      });
      setSelectedUser(null);
      setNewFee("");
      setReason("");
    }
  };

  const handleUpdateGlobalFee = async () => {
    const feeValue = newFee === "" ? null : parseFloat(newFee);

    // Preview first
    const preview = await previewGlobal.mutateAsync(feeValue);

    if (await confirmAction(
      `Alterar taxa GLOBAL para ${brlFee(feeValue)}?\n\n` +
      `Isso afetará ${preview.affected_count} usuários.\n\n` +
      `Esta ação não pode ser desfeita facilmente. Tem certeza?`
    )) {
      await updateGlobalFee.mutateAsync({
        new_fee: feeValue,
        reason: reason || undefined,
      });
      setNewFee("");
      setReason("");
      setShowGlobalPreview(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="flex items-center gap-2 text-lg font-semibold text-fg">
          <DollarSign className="text-accent" size={20} />
          Gerenciamento de Taxas
        </h3>
        <button
          className="btn-secondary btn-sm"
          onClick={() => setShowHistory(!showHistory)}
          type="button"
        >
          <History size={16} />
          {showHistory ? "Esconder" : "Ver"} Histórico
        </button>
      </div>

      {currentFees.isLoading && <LoadingState label="Carregando taxas" />}
      {currentFees.error && (
        <ErrorState message="Não foi possível carregar as taxas." onRetry={() => void currentFees.refetch()} />
      )}

      {currentFees.data && (
        <div className="space-y-4">
          {/* Quick actions */}
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-lg border border-line-soft bg-surface-inset p-4">
              <h4 className="mb-3 flex items-center gap-2 text-sm font-semibold text-fg">
                <Users size={16} />
                Alterar taxa global
              </h4>
              <div className="space-y-2">
                <input
                  className="input w-full"
                  placeholder="Nova taxa (ex: 2.50) ou vazio para padrão"
                  type="number"
                  value={newFee}
                  onChange={(e) => setNewFee(e.target.value)}
                  step="0.01"
                  min="0"
                />
                <input
                  className="input w-full"
                  placeholder="Motivo da alteração (opcional)"
                  type="text"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
                <button
                  className="btn-primary w-full"
                  onClick={() => void handleUpdateGlobalFee()}
                  type="button"
                  disabled={updateGlobalFee.isPending}
                >
                  {updateGlobalFee.isPending ? "Alterando..." : "Alterar para todos"}
                </button>
              </div>
            </div>

            <div className="rounded-lg border border-line-soft bg-surface-inset p-4">
              <h4 className="mb-3 flex items-center gap-2 text-sm font-semibold text-fg">
                <ArrowRightLeft size={16} />
                Alterar taxa individual
              </h4>
              <div className="space-y-2">
                <select
                  className="input w-full"
                  value={selectedUser || ""}
                  onChange={(e) => setSelectedUser(e.target.value || null)}
                >
                  <option value="">Selecione um usuário</option>
                  {currentFees.data.partners.map((partner) => (
                    <option key={partner.user_id} value={partner.user_id}>
                      {partner.name} ({brlFee(partner.current_fee)})
                    </option>
                  ))}
                </select>
                <input
                  className="input w-full"
                  placeholder="Nova taxa (ex: 2.50) ou vazio para padrão"
                  type="number"
                  value={newFee}
                  onChange={(e) => setNewFee(e.target.value)}
                  step="0.01"
                  min="0"
                  disabled={!selectedUser}
                />
                <input
                  className="input w-full"
                  placeholder="Motivo da alteração (opcional)"
                  type="text"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  disabled={!selectedUser}
                />
                <button
                  className="btn-primary w-full"
                  onClick={() => void handleUpdateUserFee()}
                  type="button"
                  disabled={!selectedUser || updateUserFee.isPending}
                >
                  {updateUserFee.isPending ? "Alterando..." : "Alterar taxa"}
                </button>
              </div>
            </div>
          </div>

          {/* Current fees */}
          <div className="rounded-lg border border-line-soft bg-surface-inset p-4">
            <h4 className="mb-3 text-sm font-semibold text-fg">Sócios e suas taxas atuais</h4>
            <div className="space-y-2">
              {currentFees.data.partners.length === 0 ? (
                <p className="text-xs text-muted">Nenhum sócio cadastrado.</p>
              ) : (
                currentFees.data.partners.map((partner) => (
                  <div
                    key={partner.user_id}
                    className="flex items-center justify-between rounded-lg border border-line-soft bg-surface p-3"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-fg">{partner.name}</p>
                      <p className="truncate text-xs text-muted">
                        {partner.email} · Sócio de {partner.chief_name || "—"}
                      </p>
                    </div>
                    <div className="shrink-0 text-right">
                      <p className="text-sm font-semibold text-accent">{brlFee(partner.current_fee)}</p>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* History modal */}
      {showHistory && (
        <Modal onClose={() => setShowHistory(false)} open title="Histórico de alterações de taxas">
          <div className="space-y-3">
            {feeHistory.isLoading && <LoadingState label="Carregando histórico" />}
            {feeHistory.error && (
              <ErrorState message="Não foi possível carregar o histórico." onRetry={() => void feeHistory.refetch()} />
            )}
            {feeHistory.data && feeHistory.data.history.length === 0 && (
              <p className="text-sm text-muted">Nenhuma alteração registrada ainda.</p>
            )}
            {feeHistory.data?.history.map((log) => (
              <div key={`${log.user_id}-${log.created_at}`} className="rounded-lg border border-line-soft bg-surface-inset p-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-fg">{log.user_name}</p>
                    <p className="mt-1 text-xs text-muted">
                      {brlFee(log.old_fee)} → {brlFee(log.new_fee)}
                    </p>
                    {log.reason && <p className="mt-1 text-xs text-muted">Motivo: {log.reason}</p>}
                    <p className="mt-1 text-xs text-muted">
                      Por {log.changed_by || "Sistema"} · {new Date(log.created_at).toLocaleString("pt-BR")}
                    </p>
                  </div>
                  {log.is_global_change && (
                    <span className="shrink-0 rounded-md bg-warning-soft px-2 py-1 text-[10px] font-medium text-warning">
                      Global
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Modal>
      )}
    </div>
  );
}
