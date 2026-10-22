import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, FolderTree, Pencil, Plus, Shuffle, Trash2 } from "lucide-react";

import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { confirmAction } from "@/lib/confirm";
import { ApiError, apiRequest } from "@/services/api";
import type { Flow, SharedFlowOption } from "./types";

export type FlowFolder = {
  id: string;
  name: string;
  flows: { id: string; name: string; shared: boolean }[];
  bots: string[];
};

const errorText = (error: unknown) => (error instanceof ApiError ? error.message : "Não foi possível concluir a ação.");

export function useFolders(enabled = true) {
  return useQuery({
    queryKey: ["bots", "folders"],
    queryFn: () => apiRequest<{ folders: FlowFolder[] }>("/api/bots/folders"),
    enabled,
  });
}

/** Falcon Bot > Pastas de funis: funnels to test against each other; a bot connected to a
 *  folder gives each new lead one of them at random (the lead keeps it). */
export function FoldersPanel() {
  const queryClient = useQueryClient();
  const folders = useFolders();
  const [editing, setEditing] = useState<FlowFolder | "new" | null>(null);
  const remove = useMutation({
    mutationFn: (id: string) => apiRequest(`/api/bots/folders/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["bots"] });
    },
  });

  if (folders.isLoading) return <LoadingState label="Carregando pastas" />;
  if (folders.error) return <ErrorState message={errorText(folders.error)} onRetry={() => void folders.refetch()} />;
  const list = folders.data?.folders ?? [];

  return (
    <div className="space-y-4">
      <div className="dashboard-card flex flex-wrap items-center justify-between gap-3 p-4">
        <p className="flex max-w-3xl items-start gap-2 text-xs leading-5 text-muted">
          <Shuffle className="mt-0.5 shrink-0 text-accent" size={15} />
          Cada lead novo recebe um funil da pasta, sorteado no /start, e continua nele. Assim os números de cada funil ficam comparáveis na aba
          Estratégia. Conecte o robô à pasta em Meus robôs.
        </p>
        <Button onClick={() => setEditing("new")} variant="primary">
          <Plus size={15} /> Nova pasta
        </Button>
      </div>
      {remove.error && <ErrorState message={errorText(remove.error)} />}
      {list.length === 0 ? (
        <EmptyState message="Nenhuma pasta ainda. Crie uma com dois ou mais funis para testar qual vende mais." />
      ) : (
        <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
          {list.map((folder) => (
            <article className="dashboard-card space-y-3 p-4" key={folder.id}>
              <div className="flex items-start justify-between gap-2">
                <p className="flex min-w-0 items-center gap-2 font-semibold text-fg">
                  <FolderTree className="shrink-0 text-accent" size={16} />
                  <span className="truncate">{folder.name}</span>
                </p>
                <Badge tone={folder.flows.length >= 2 ? "success" : "warning"}>{folder.flows.length} funil(is)</Badge>
              </div>
              <ul className="space-y-1">
                {folder.flows.map((flow) => (
                  <li className="flex items-center justify-between gap-2 rounded-lg bg-surface-inset px-2.5 py-1.5 text-xs text-fg" key={flow.id}>
                    <span className="truncate">{flow.name}</span>
                    {flow.shared && <span className="shrink-0 text-[10px] text-muted">compartilhado</span>}
                  </li>
                ))}
                {folder.flows.length === 0 && <li className="text-xs text-muted">Pasta vazia: o robô conectado não responde.</li>}
              </ul>
              <p className="flex items-center gap-1.5 text-[11px] text-muted">
                <Bot size={12} />
                {folder.bots.length ? folder.bots.map((name) => `@${name}`).join(", ") : "Nenhum robô conectado"}
              </p>
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => setEditing(folder)} size="sm">
                  <Pencil size={14} /> Editar
                </Button>
                <Link className="btn-ghost btn-sm" to="/bot/estrategia">Ver estratégia</Link>
                <Button
                  disabled={remove.isPending}
                  onClick={async () => {
                    if (await confirmAction({ title: `Excluir a pasta “${folder.name}”?`, message: "Os robôs conectados a ela param de enviar funis até você escolher outro funil ou pasta. Os leads mantêm o funil que receberam.", danger: true })) {
                      remove.mutate(folder.id);
                    }
                  }}
                  size="sm"
                  variant="ghost"
                >
                  <Trash2 size={14} /> Excluir
                </Button>
              </div>
            </article>
          ))}
        </div>
      )}
      <FolderModal folder={editing} onClose={() => setEditing(null)} />
    </div>
  );
}

function FolderModal({ folder, onClose }: { folder: FlowFolder | "new" | null; onClose: () => void }) {
  const queryClient = useQueryClient();
  const flows = useQuery({
    queryKey: ["bots", "flows"],
    queryFn: () => apiRequest<{ flows: Flow[]; shared_flows?: SharedFlowOption[] }>("/api/bots/flows/list"),
    enabled: folder !== null,
  });
  const [name, setName] = useState("");
  const [picked, setPicked] = useState<Set<string>>(new Set());
  useEffect(() => {
    if (folder === null) return;
    setName(folder === "new" ? "" : folder.name);
    setPicked(new Set(folder === "new" ? [] : folder.flows.map((flow) => flow.id)));
  }, [folder]);
  const save = useMutation({
    mutationFn: () =>
      folder === "new" || folder === null
        ? apiRequest("/api/bots/folders", { method: "POST", body: { name: name.trim(), flow_ids: [...picked] } })
        : apiRequest(`/api/bots/folders/${folder.id}`, { method: "PUT", body: { name: name.trim(), flow_ids: [...picked] } }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["bots"] });
      onClose();
    },
  });
  if (folder === null) return null;
  const options = [
    ...(flows.data?.flows ?? []).map((flow) => ({ id: flow.id, name: flow.name, shared: false })),
    ...(flows.data?.shared_flows ?? []).map((flow) => ({ id: flow.id, name: flow.name, shared: true })),
  ];
  const flip = (id: string) =>
    setPicked((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <Modal
      busy={save.isPending}
      description="Escolha os funis que entram no sorteio. Funis compartilhados com você também podem entrar."
      footer={
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>Cancelar</Button>
          <Button disabled={!name.trim() || save.isPending} onClick={() => save.mutate()} variant="primary">
            {save.isPending ? "Salvando…" : "Salvar pasta"}
          </Button>
        </div>
      }
      onClose={onClose}
      open
      title={folder === "new" ? "Nova pasta de funis" : `Editar “${folder.name}”`}
    >
      <div className="space-y-4">
        <label className="block space-y-1.5">
          <span className="text-sm font-medium text-fg">Nome</span>
          <input className="field" maxLength={120} onChange={(e) => setName(e.target.value)} placeholder="ex.: Teste de prévias" value={name} />
        </label>
        <fieldset className="space-y-1.5">
          <legend className="text-sm font-medium text-fg">Funis da pasta</legend>
          {flows.isLoading && <LoadingState label="Carregando funis" />}
          {flows.data && options.length === 0 && <p className="text-xs text-muted">Crie um funil em Meus funis primeiro.</p>}
          <div className="grid gap-1.5 sm:grid-cols-2">
            {options.map((flow) => (
              <label className="flex items-center gap-2 rounded-lg border border-line-soft px-2.5 py-2 text-sm text-fg" key={flow.id}>
                <input checked={picked.has(flow.id)} onChange={() => flip(flow.id)} type="checkbox" />
                <span className="min-w-0 truncate">{flow.name}</span>
                {flow.shared && <span className="ml-auto shrink-0 text-[10px] text-muted">compartilhado</span>}
              </label>
            ))}
          </div>
          {picked.size === 1 && <p className="text-[11px] text-warning">Com um funil só não há teste: todos os leads recebem o mesmo.</p>}
        </fieldset>
        {save.error && <ErrorState message={errorText(save.error)} />}
      </div>
    </Modal>
  );
}
