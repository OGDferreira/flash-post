import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FolderPlus, Pencil, Trash2 } from "lucide-react";

import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Modal } from "@/components/ui/Modal";
import { confirmAction } from "@/lib/confirm";
import { ApiError, apiRequest } from "@/services/api";
import type { Flow } from "./types";

type Folder = { id: string; name: string; bots: number; flows: { id: string; name: string }[] };

/** Pastas de funis: um bot pode rodar uma pasta inteira e cada lead recebe um funil sorteado. */
export function FoldersPanel() {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<Folder | null | "new">(null);
  const folders = useQuery({ queryKey: ["bots", "folders"], queryFn: () => apiRequest<{ folders: Folder[] }>("/api/bots/folders") });
  const remove = useMutation({
    mutationFn: (id: string) => apiRequest(`/api/bots/folders/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["bots", "folders"] });
      void queryClient.invalidateQueries({ queryKey: ["bots"] });
    },
  });

  if (folders.isLoading) return <LoadingState label="Carregando pastas" />;
  if (folders.error) return <ErrorState message="Não foi possível carregar as pastas." onRetry={() => void folders.refetch()} />;
  const list = folders.data!.folders;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm text-muted">
          Uma pasta junta vários funis. O bot ligado a uma pasta dá a cada novo lead um funil sorteado no /start, e o lead continua
          nele. Compare o desempenho em Análises.
        </p>
        <Button onClick={() => setEditing("new")} variant="primary"><FolderPlus size={15} /> Nova pasta</Button>
      </div>
      {list.length === 0 ? (
        <EmptyState message="Nenhuma pasta ainda. Crie uma e escolha os funis que entram no sorteio." />
      ) : (
        <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
          {list.map((folder) => (
            <Card className="space-y-3" key={folder.id}>
              <div className="flex items-start justify-between gap-2">
                <p className="min-w-0 truncate font-medium text-fg">📁 {folder.name}</p>
                <span className="shrink-0 text-xs text-muted">{folder.bots} bot(s)</span>
              </div>
              <ul className="space-y-1 text-sm text-fg-2">
                {folder.flows.length === 0 ? (
                  <li className="text-xs text-warning">Sem funis — adicione para o sorteio funcionar.</li>
                ) : (
                  folder.flows.map((flow) => <li key={flow.id} className="truncate">• {flow.name}</li>)
                )}
              </ul>
              <div className="flex gap-2">
                <Button onClick={() => setEditing(folder)} size="sm"><Pencil size={14} /> Editar</Button>
                <Button
                  disabled={remove.isPending}
                  onClick={async () => {
                    if (await confirmAction(`Excluir a pasta "${folder.name}"? Os bots nela ficam sem funil; os leads mantêm o que já tinham.`)) {
                      remove.mutate(folder.id);
                    }
                  }}
                  size="sm"
                  variant="ghost"
                >
                  <Trash2 size={14} /> Excluir
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}
      <FolderModal folder={editing === "new" ? null : editing} open={editing !== null} onClose={() => setEditing(null)} />
    </div>
  );
}

function FolderModal({ folder, open, onClose }: { folder: Folder | null; open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const flows = useQuery({
    queryKey: ["bots", "flows"],
    queryFn: () => apiRequest<{ flows: Flow[] }>("/api/bots/flows/list"),
    enabled: open,
  });
  const save = useMutation({
    mutationFn: () =>
      apiRequest(folder ? `/api/bots/folders/${folder.id}` : "/api/bots/folders", {
        method: folder ? "PUT" : "POST",
        body: { name: name.trim(), flow_ids: [...picked] },
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["bots", "folders"] });
      void queryClient.invalidateQueries({ queryKey: ["bots"] });
      onClose();
    },
  });

  // Reset the form each time the modal opens for a different folder.
  const openedFor = folder?.id ?? "new";
  const [lastOpened, setLastOpened] = useState<string | null>(null);
  if (open && lastOpened !== openedFor) {
    setLastOpened(openedFor);
    setName(folder?.name ?? "");
    setPicked(new Set(folder?.flows.map((flow) => flow.id) ?? []));
    save.reset();
  }
  if (!open && lastOpened !== null) setLastOpened(null);

  const ownFlows = (flows.data?.flows ?? []).filter((flow) => !flow.from_template);
  const toggle = (id: string) =>
    setPicked((current) => {
      const next = new Set(current);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  return (
    <Modal
      busy={save.isPending}
      description="Os leads do bot ligado a esta pasta recebem um destes funis, sorteado no /start."
      footer={
        <div className="flex flex-wrap justify-end gap-2">
          <Button onClick={onClose}>Cancelar</Button>
          <Button disabled={!name.trim() || picked.size === 0 || save.isPending} onClick={() => save.mutate()} variant="primary">
            {save.isPending ? "Salvando…" : folder ? "Salvar" : "Criar pasta"}
          </Button>
        </div>
      }
      onClose={onClose}
      open={open}
      title={folder ? "Editar pasta" : "Nova pasta"}
    >
      <div className="space-y-3">
        <label className="block space-y-1.5">
          <span className="text-sm font-medium text-fg">Nome da pasta</span>
          <input className="field" onChange={(event) => setName(event.target.value)} placeholder="ex.: Teste A/B" value={name} />
        </label>
        <div className="space-y-1.5">
          <span className="text-sm font-medium text-fg">Funis no sorteio</span>
          {flows.isLoading ? (
            <LoadingState label="Carregando funis" />
          ) : ownFlows.length === 0 ? (
            <p className="text-xs text-muted">Você ainda não tem funis próprios para colocar na pasta.</p>
          ) : (
            <ul className="max-h-64 space-y-1 overflow-auto rounded-xl border border-line-soft p-2">
              {ownFlows.map((flow) => (
                <li key={flow.id}>
                  <label className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-sm text-fg hover:bg-surface-inset">
                    <input checked={picked.has(flow.id)} className="size-4 accent-[var(--color-accent)]" onChange={() => toggle(flow.id)} type="checkbox" />
                    <span className="truncate">{flow.name}</span>
                  </label>
                </li>
              ))}
            </ul>
          )}
          <span className="block text-[11px] text-muted">{picked.size} funil(is) selecionado(s).</span>
        </div>
        {save.error && <ErrorState message={save.error instanceof ApiError ? save.error.message : "Não foi possível salvar."} />}
      </div>
    </Modal>
  );
}
