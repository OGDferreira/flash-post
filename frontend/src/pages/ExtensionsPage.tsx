import { useRef, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Eye, EyeOff, Pencil, Plus, Puzzle, Trash2, Upload } from "lucide-react";

import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { Modal } from "@/components/ui/Modal";
import { useAuth } from "@/features/auth/AuthProvider";
import { ApiError, apiRequest } from "@/services/api";
import { confirmAction } from "@/lib/confirm";

type Extension = {
  id: string;
  name: string;
  description: string | null;
  instructions: string | null;
  visible_to_collaborators: boolean;
  file_name: string | null;
  file_size: number | null;
  has_file: boolean;
  updated_at: string;
};

const MAX_BYTES = 25 * 1024 * 1024;
const errorText = (error: unknown) => (error instanceof ApiError ? error.message : "Não foi possível concluir a ação.");
const sizeLabel = (bytes: number | null) =>
  bytes === null ? "—" : bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;

function EditorModal({ item, open, onClose }: { item: Extension | null; open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const [name, setName] = useState(item?.name ?? "");
  const [description, setDescription] = useState(item?.description ?? "");
  const [instructions, setInstructions] = useState(item?.instructions ?? "");
  const [visible, setVisible] = useState(item?.visible_to_collaborators ?? true);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: async () => {
      const body = {
        name: name.trim(),
        description: description.trim() || null,
        instructions: instructions.trim() || null,
        visible_to_collaborators: visible,
      };
      const saved = item
        ? await apiRequest<Extension>(`/api/extensions/${item.id}`, { method: "PATCH", body })
        : await apiRequest<Extension>("/api/extensions", { method: "POST", body });
      if (file) {
        await apiRequest<Extension>(`/api/extensions/${saved.id}/file`, {
          method: "PUT",
          headers: { "Content-Type": "application/zip", "X-File-Name": file.name },
          body: file,
        });
      }
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["extensions"] });
      onClose();
    },
    onError: (e) => setError(errorText(e)),
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (name.trim().length < 2) return setError("Informe um nome com pelo menos 2 caracteres.");
    if (!item && !file) return setError("Selecione o arquivo ZIP.");
    save.mutate();
  };

  const pick = (selected: File | null) => {
    if (!selected) return;
    if (!/\.zip$/i.test(selected.name)) return setError("Selecione um arquivo .zip.");
    if (selected.size > MAX_BYTES) return setError("O ZIP deve ter até 25 MB.");
    setError(null);
    setFile(selected);
  };

  return (
    <Modal
      busy={save.isPending}
      description="Somente arquivos ZIP, até 25 MB."
      onClose={onClose}
      open={open}
      title={item ? "Editar extensão" : "Nova extensão"}
      footer={
        <>
          <button className="btn-ghost" disabled={save.isPending} onClick={onClose} type="button">Cancelar</button>
          <button className="btn-primary" disabled={save.isPending} form="extension-form" type="submit">
            {save.isPending ? "Salvando…" : "Salvar"}
          </button>
        </>
      }
    >
      <form className="space-y-3" id="extension-form" onSubmit={submit}>
        <label className="block text-sm">
          <span className="mb-1 block text-fg-2">Nome</span>
          <input className="field" maxLength={120} onChange={(e) => setName(e.target.value)} value={name} />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-fg-2">Descrição</span>
          <input className="field" maxLength={1000} onChange={(e) => setDescription(e.target.value)} value={description} />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-fg-2">Instruções de instalação/uso</span>
          <textarea className="field min-h-24 py-2" maxLength={8000} onChange={(e) => setInstructions(e.target.value)} value={instructions} />
        </label>
        <label className="flex items-center gap-2 text-sm text-fg-2">
          <input checked={visible} onChange={(e) => setVisible(e.target.checked)} type="checkbox" />
          Colaboradores podem baixar
        </label>
        <div>
          <input accept=".zip,application/zip" className="hidden" onChange={(e) => { pick(e.target.files?.[0] ?? null); e.target.value = ""; }} ref={fileInput} type="file" />
          <button className="btn-secondary" onClick={() => fileInput.current?.click()} type="button">
            <Upload size={15} /> {item ? "Trocar ZIP" : "Escolher ZIP"}
          </button>
          <span className="ml-2 text-xs text-muted">{file ? `${file.name} (${sizeLabel(file.size)})` : item?.file_name ?? ""}</span>
        </div>
        {error && <p className="text-xs text-danger" role="alert">{error}</p>}
      </form>
    </Modal>
  );
}

export function ExtensionsPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const isOwner = user?.role === "OWNER" || (user?.role === "SUPER_ADMIN" && user.workspace_role === "OWNER");
  const [editing, setEditing] = useState<Extension | null | undefined>(undefined);
  const [actionError, setActionError] = useState<string | null>(null);

  const list = useQuery({
    queryKey: ["extensions"],
    queryFn: () => apiRequest<Extension[]>("/api/extensions"),
  });
  const remove = useMutation({
    mutationFn: (id: string) => apiRequest<void>(`/api/extensions/${id}`, { method: "DELETE" }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["extensions"] }),
    onError: (e) => setActionError(errorText(e)),
  });

  return (
    <div className="mx-auto max-w-[1100px] space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="mt-1 flex items-center gap-2 text-2xl font-semibold tracking-[-0.045em] text-fg">
            <Puzzle className="text-accent" size={24} /> Extensões
          </h2>
        </div>
        {isOwner && (
          <button className="btn-primary" onClick={() => setEditing(null)} type="button">
            <Plus size={16} /> Nova extensão
          </button>
        )}
      </header>

      {list.isLoading && <LoadingState label="Carregando extensões" />}
      {list.error && <ErrorState message={errorText(list.error)} onRetry={() => void list.refetch()} />}
      {actionError && <ErrorState message={actionError} />}
      {list.data && list.data.length === 0 && (
        <EmptyState message={isOwner ? "Nenhuma extensão enviada ainda." : "Nenhuma extensão liberada para você."} icon={<Puzzle size={18} />} />
      )}

      <div className="grid gap-3 md:grid-cols-2">
        {list.data?.map((item) => (
          <article className="glass-panel space-y-2 p-4" key={item.id}>
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <h3 className="truncate font-medium text-fg">{item.name}</h3>
                {item.description && <p className="mt-0.5 text-sm text-muted">{item.description}</p>}
              </div>
              {isOwner && (
                <span className="flex shrink-0 items-center gap-1 text-xs text-muted" title={item.visible_to_collaborators ? "Visível para colaboradores" : "Oculta para colaboradores"}>
                  {item.visible_to_collaborators ? <Eye size={14} /> : <EyeOff size={14} />}
                </span>
              )}
            </div>
            {item.instructions && (
              <p className="whitespace-pre-wrap rounded-lg bg-black/25 p-2.5 text-xs leading-5 text-fg-2">{item.instructions}</p>
            )}
            <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
              <span className="text-xs text-muted">
                {item.has_file ? `${item.file_name} · ${sizeLabel(item.file_size)}` : "Sem arquivo"}
              </span>
              <span className="flex gap-1.5">
                {item.has_file && (
                  <a className="btn-secondary" download href={`/api/extensions/${item.id}/download`}>
                    <Download size={15} /> Baixar
                  </a>
                )}
                {isOwner && (
                  <>
                    <button aria-label="Editar" className="btn-ghost" onClick={() => setEditing(item)} type="button"><Pencil size={15} /></button>
                    <button
                      aria-label="Excluir"
                      className="btn-ghost"
                      disabled={remove.isPending}
                      onClick={async () => { if (await confirmAction(`Excluir "${item.name}"?`)) { setActionError(null); remove.mutate(item.id); } }}
                      type="button"
                    >
                      <Trash2 size={15} />
                    </button>
                  </>
                )}
              </span>
            </div>
          </article>
        ))}
      </div>

      {editing !== undefined && (
        <EditorModal item={editing} key={editing?.id ?? "new"} onClose={() => setEditing(undefined)} open />
      )}
    </div>
  );
}
