import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LifeBuoy, Plus } from "lucide-react";

import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { Modal } from "@/components/ui/Modal";
import { useAuth } from "@/features/auth/AuthProvider";
import { ApiError, apiRequest } from "@/services/api";

type Status = "OPEN" | "IN_PROGRESS" | "RESOLVED" | "CLOSED";
type Ticket = {
  id: string;
  kind: "QUESTION" | "PROBLEM";
  title: string;
  description: string;
  status: Status;
  resolution_note: string | null;
  author_name: string;
  is_mine: boolean;
  can_manage: boolean;
  created_at: string;
  resolved_at: string | null;
};
type Listing = { scope: string; total: number; counts: Record<Status, number>; items: Ticket[] };

const STATUS_LABEL: Record<Status, string> = {
  OPEN: "Aberto",
  IN_PROGRESS: "Em andamento",
  RESOLVED: "Resolvido",
  CLOSED: "Encerrado",
};
const STATUS_TONE: Record<Status, string> = {
  OPEN: "text-accent border-brand/40",
  IN_PROGRESS: "text-warning border-warning/40",
  RESOLVED: "text-success border-success/40",
  CLOSED: "text-muted border-line",
};
const errorText = (error: unknown) => (error instanceof ApiError ? error.message : "Não foi possível concluir a ação.");
const when = (iso: string) => new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });

function NewTicketModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [kind, setKind] = useState<"QUESTION" | "PROBLEM">("QUESTION");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: () => apiRequest<Ticket>("/api/support/tickets", { method: "POST", body: { kind, title: title.trim(), description: description.trim() } }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["support"] });
      onClose();
    },
    onError: (e) => setError(errorText(e)),
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (title.trim().length < 3) return setError("Informe um título com pelo menos 3 caracteres.");
    if (description.trim().length < 5) return setError("Descreva a dúvida ou o problema.");
    create.mutate();
  };
  return (
    <Modal
      busy={create.isPending}
      onClose={onClose}
      open
      title="Novo registro"
      footer={
        <>
          <button className="btn-ghost" disabled={create.isPending} onClick={onClose} type="button">Cancelar</button>
          <button className="btn-primary" disabled={create.isPending} form="ticket-form" type="submit">{create.isPending ? "Enviando…" : "Enviar"}</button>
        </>
      }
    >
      <form className="space-y-3" id="ticket-form" onSubmit={submit}>
        <div className="flex gap-2" role="radiogroup" aria-label="Tipo">
          {(["QUESTION", "PROBLEM"] as const).map((value) => (
            <button
              aria-checked={kind === value}
              className={kind === value ? "btn-primary" : "btn-secondary"}
              key={value}
              onClick={() => setKind(value)}
              role="radio"
              type="button"
            >
              {value === "QUESTION" ? "Dúvida" : "Erro / problema"}
            </button>
          ))}
        </div>
        <label className="block text-sm">
          <span className="mb-1 block text-fg-2">Título</span>
          <input className="field" maxLength={160} onChange={(e) => setTitle(e.target.value)} value={title} />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-fg-2">Descrição</span>
          <textarea className="field min-h-28 py-2" maxLength={5000} onChange={(e) => setDescription(e.target.value)} value={description} />
        </label>
        {error && <p className="text-xs text-danger" role="alert">{error}</p>}
      </form>
    </Modal>
  );
}

function TicketCard({ ticket }: { ticket: Ticket }) {
  const queryClient = useQueryClient();
  const [note, setNote] = useState(ticket.resolution_note ?? "");
  const [error, setError] = useState<string | null>(null);
  const update = useMutation({
    mutationFn: (body: { status?: Status; resolution_note?: string }) =>
      apiRequest<Ticket>(`/api/support/tickets/${ticket.id}`, { method: "PATCH", body }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["support"] }),
    onError: (e) => setError(errorText(e)),
  });
  const closed = ticket.status === "CLOSED";
  return (
    <article className="glass-panel space-y-2 p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="font-medium text-fg">{ticket.title}</h3>
          <p className="text-xs text-muted">
            {ticket.kind === "QUESTION" ? "Dúvida" : "Erro / problema"} · {ticket.author_name} · {when(ticket.created_at)}
          </p>
        </div>
        <span className={`rounded-full border px-2.5 py-0.5 text-xs ${STATUS_TONE[ticket.status]}`}>{STATUS_LABEL[ticket.status]}</span>
      </div>
      <p className="whitespace-pre-wrap text-sm leading-6 text-fg-2">{ticket.description}</p>
      {ticket.resolution_note && !ticket.can_manage && (
        <p className="rounded-lg bg-black/25 p-2.5 text-sm text-fg-2"><strong className="text-success">Resposta:</strong> {ticket.resolution_note}</p>
      )}
      {ticket.can_manage && (
        <div className="space-y-2 border-t border-line-soft pt-2">
          <textarea className="field min-h-16 py-2 text-sm" maxLength={5000} onChange={(e) => setNote(e.target.value)} placeholder="Resposta / observação" value={note} />
          <div className="flex flex-wrap gap-1.5">
            {(Object.keys(STATUS_LABEL) as Status[]).map((status) => (
              <button
                className={ticket.status === status ? "btn-primary" : "btn-secondary"}
                disabled={update.isPending}
                key={status}
                onClick={() => { setError(null); update.mutate({ status, resolution_note: note }); }}
                type="button"
              >
                {STATUS_LABEL[status]}
              </button>
            ))}
          </div>
        </div>
      )}
      {!ticket.can_manage && ticket.is_mine && !closed && (
        <button className="btn-ghost" disabled={update.isPending} onClick={() => { setError(null); update.mutate({ status: "CLOSED" }); }} type="button">
          Encerrar chamado
        </button>
      )}
      {error && <p className="text-xs text-danger" role="alert">{error}</p>}
    </article>
  );
}

export function SupportPage() {
  const { user } = useAuth();
  const isOwner = user?.role === "OWNER" || (user?.role === "SUPER_ADMIN" && user.workspace_role === "OWNER");
  const [scope, setScope] = useState<"mine" | "workspace">("mine");
  const [status, setStatus] = useState<Status | "">("");
  const [creating, setCreating] = useState(false);
  const list = useQuery({
    queryKey: ["support", scope, status],
    queryFn: () => apiRequest<Listing>(`/api/support/tickets?scope=${scope}&page_size=50${status ? `&status=${status}` : ""}`),
  });
  return (
    <div className="mx-auto max-w-[900px] space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="mt-1 flex items-center gap-2 text-2xl font-semibold tracking-[-0.045em] text-fg">
            <LifeBuoy className="text-accent" size={24} /> Dúvidas e erros
          </h2>
        </div>
        <button className="btn-primary" onClick={() => setCreating(true)} type="button"><Plus size={16} /> Novo registro</button>
      </header>

      <div className="flex flex-wrap items-center gap-2">
        {isOwner && (
          <div className="flex gap-1.5">
            <button className={scope === "mine" ? "btn-primary" : "btn-secondary"} onClick={() => setScope("mine")} type="button">Meus</button>
            <button className={scope === "workspace" ? "btn-primary" : "btn-secondary"} onClick={() => setScope("workspace")} type="button">Dos colaboradores</button>
          </div>
        )}
        <div className="flex flex-wrap gap-1.5">
          <button className={status === "" ? "btn-primary" : "btn-secondary"} onClick={() => setStatus("")} type="button">Todos</button>
          {(Object.keys(STATUS_LABEL) as Status[]).map((value) => (
            <button className={status === value ? "btn-primary" : "btn-secondary"} key={value} onClick={() => setStatus(value)} type="button">
              {STATUS_LABEL[value]}{list.data ? ` (${list.data.counts[value]})` : ""}
            </button>
          ))}
        </div>
      </div>

      {list.isLoading && <LoadingState label="Carregando registros" />}
      {list.error && <ErrorState message={errorText(list.error)} onRetry={() => void list.refetch()} />}
      {list.data && list.data.items.length === 0 && <EmptyState message="Nenhum registro por aqui." icon={<LifeBuoy size={18} />} />}
      <div className="space-y-3">
        {list.data?.items.map((ticket) => <TicketCard key={`${ticket.id}-${ticket.status}`} ticket={ticket} />)}
      </div>
      {creating && <NewTicketModal onClose={() => setCreating(false)} />}
    </div>
  );
}
