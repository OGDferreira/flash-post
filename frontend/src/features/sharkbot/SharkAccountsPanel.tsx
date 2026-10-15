import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, RefreshCw, Save, Trash2, X } from "lucide-react";

import { CopyField } from "@/components/ui/CopyField";
import { ErrorState, LoadingState } from "@/components/PageState";
import { formatDateTime } from "@/features/analytics/period";
import { ApiError, apiRequest } from "@/services/api";
import { confirmAction } from "@/lib/confirm";

export type SharkAccount = {
  id: string | null;
  name: string;
  external_account_id: string | null;
  webhook_url: string;
  is_active: boolean;
  is_default: boolean;
  last_event_at: string | null;
};

export const sharkAccountsKey = ["sharkbot", "accounts"] as const;

export function useSharkAccounts(enabled = true) {
  return useQuery({
    queryKey: sharkAccountsKey,
    queryFn: () => apiRequest<SharkAccount[]>("/api/sharkbot/accounts"),
    enabled,
    staleTime: 60_000,
  });
}

const message = (error: unknown) => (error instanceof ApiError ? error.message : "Não foi possível concluir a ação.");

export function SharkAccountsPanel() {
  const queryClient = useQueryClient();
  const accounts = useSharkAccounts();
  const [name, setName] = useState("");
  const [externalId, setExternalId] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editExternal, setEditExternal] = useState("");
  const refresh = () => void queryClient.invalidateQueries({ queryKey: sharkAccountsKey });

  const create = useMutation({
    mutationFn: () =>
      apiRequest<SharkAccount>("/api/sharkbot/accounts", {
        method: "POST",
        body: { name, external_account_id: externalId || null },
      }),
    onSuccess: () => {
      setName("");
      setExternalId("");
      refresh();
    },
  });
  const update = useMutation({
    mutationFn: (id: string) =>
      apiRequest<SharkAccount>(`/api/sharkbot/accounts/${id}`, {
        method: "PATCH",
        body: { name: editName, external_account_id: editExternal || null },
      }),
    onSuccess: () => {
      setEditing(null);
      refresh();
    },
  });
  const rotate = useMutation({
    mutationFn: (id: string) => apiRequest(`/api/sharkbot/accounts/${id}/rotate`, { method: "POST" }),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: (id: string) => apiRequest(`/api/sharkbot/accounts/${id}`, { method: "DELETE" }),
    onSuccess: refresh,
  });
  const error = create.error ?? update.error ?? rotate.error ?? remove.error;

  return (
    <section className="glass-panel space-y-4 p-4 sm:p-5">
      <div>
        <h3 className="font-medium text-fg">Contas Shark</h3>
        <p className="mt-2 text-sm leading-6 text-muted">
          Cadastre uma conta Shark por loja/operação. Cada uma tem a própria URL de webhook, e cada venda mostra de qual
          conta veio. O mesmo evento recebido duas vezes (ou por duas URLs) conta uma única vez.
        </p>
        <p className="mt-2 rounded-xl border border-warning/30/60 bg-warning-soft/60 p-3 text-xs leading-5 text-warning">
          Só o ID da conta Shark não faz as compras chegarem ao FlashPost: o SharkBot envia os eventos por webhook. Cole
          a URL da conta no campo de webhook do SharkBot e ative os eventos de entrada de lead, PIX gerado e pagamento
          aprovado. O ID abaixo é opcional e serve só para você identificar a conta.
        </p>
      </div>
      {error && <ErrorState message={message(error)} />}
      {accounts.isLoading && <LoadingState label="Carregando contas Shark" />}
      {accounts.error && <ErrorState message="Não foi possível carregar as contas Shark." onRetry={() => void accounts.refetch()} />}
      <ul className="space-y-3">
        {accounts.data?.map((account) => (
          <li className="rounded-xl border border-line-soft bg-surface-inset p-4" key={account.id ?? "default"}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              {editing === account.id && account.id ? (
                <div className="flex flex-1 flex-wrap gap-2">
                  <input aria-label="Nome" className="field !min-h-9 min-w-40 flex-1 !text-sm" maxLength={80} onChange={(e) => setEditName(e.target.value)} value={editName} />
                  <input aria-label="ID da conta Shark (opcional)" className="field !min-h-9 min-w-40 flex-1 !text-sm" maxLength={120} onChange={(e) => setEditExternal(e.target.value)} placeholder="ID na Shark (opcional)" value={editExternal} />
                  <button className="btn-primary !min-h-9" disabled={update.isPending || !editName.trim()} onClick={() => update.mutate(account.id!)} type="button"><Save size={14} />Salvar</button>
                  <button aria-label="Cancelar" className="btn-ghost !min-h-9 !px-2" onClick={() => setEditing(null)} type="button"><X size={15} /></button>
                </div>
              ) : (
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-fg">
                    {account.name}
                    {account.is_default && <span className="ml-2 rounded-full bg-brand/20 px-2 py-0.5 text-[10px] text-accent">padrão</span>}
                  </p>
                  <p className="mt-0.5 text-[11px] text-muted">
                    {account.external_account_id ? `ID Shark: ${account.external_account_id} · ` : ""}
                    {account.is_default
                      ? "Recebe eventos que chegam pela URL antiga do workspace."
                      : account.last_event_at
                        ? `Último evento: ${formatDateTime(account.last_event_at)}`
                        : "Nenhum evento recebido ainda."}
                  </p>
                </div>
              )}
              {account.id && editing !== account.id && (
                <div className="flex gap-1">
                  <button aria-label={`Editar ${account.name}`} className="btn-ghost !min-h-9 !px-2" onClick={() => { setEditing(account.id); setEditName(account.name); setEditExternal(account.external_account_id ?? ""); }} type="button"><Pencil size={14} /></button>
                  <button
                    aria-label={`Gerar nova URL de ${account.name}`}
                    className="btn-ghost !min-h-9 !px-2"
                    disabled={rotate.isPending}
                    onClick={async () => { if (await confirmAction("A URL atual deixará de funcionar. Atualize-a no SharkBot. Continuar?")) rotate.mutate(account.id!); }}
                    type="button"
                  ><RefreshCw size={14} /></button>
                  <button
                    aria-label={`Remover ${account.name}`}
                    className="btn-ghost !min-h-9 !px-2 text-danger"
                    disabled={remove.isPending}
                    onClick={async () => { if (await confirmAction(`Remover "${account.name}"? As vendas já recebidas são mantidas.`)) remove.mutate(account.id!); }}
                    type="button"
                  ><Trash2 size={14} /></button>
                </div>
              )}
            </div>
            <div className="mt-3">
              <CopyField label="URL do webhook" value={account.webhook_url} />
            </div>
          </li>
        ))}
      </ul>
      <form
        className="flex flex-wrap items-end gap-2 border-t border-line-soft pt-4"
        onSubmit={(event) => {
          event.preventDefault();
          if (name.trim()) create.mutate();
        }}
      >
        <label className="grid min-w-40 flex-1 gap-1 text-xs text-muted">
          Nome da conta Shark
          <input className="field" maxLength={80} onChange={(e) => setName(e.target.value)} placeholder="Ex.: Loja principal" required value={name} />
        </label>
        <label className="grid min-w-40 flex-1 gap-1 text-xs text-muted">
          ID na Shark (opcional)
          <input className="field" maxLength={120} onChange={(e) => setExternalId(e.target.value)} value={externalId} />
        </label>
        <button className="btn-primary" disabled={create.isPending || !name.trim()} type="submit">
          <Plus size={15} />
          {create.isPending ? "Criando..." : "Adicionar conta"}
        </button>
      </form>
    </section>
  );
}
