import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Link2, Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { ErrorState, LoadingState } from "@/components/PageState";
import { useAuth } from "@/features/auth/AuthProvider";
import { ApiError, apiRequest } from "@/services/api";

type UsefulLink = { title: string; url: string; description: string };

const errorText = (error: unknown) => (error instanceof ApiError ? error.message : "Não foi possível salvar os links.");

/** Super Admin editor: the whole list is saved at once. */
function LinksEditor({ links, onDone }: { links: UsefulLink[]; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<UsefulLink[]>(links.length ? links : [{ title: "", url: "", description: "" }]);
  const save = useMutation({
    mutationFn: (items: UsefulLink[]) => apiRequest<{ links: UsefulLink[] }>("/api/links", { method: "PUT", body: { links: items } }),
    onSuccess: (data) => {
      queryClient.setQueryData(["links"], data);
      onDone();
    },
  });
  const update = (index: number, field: keyof UsefulLink, value: string) =>
    setDraft((items) => items.map((item, position) => (position === index ? { ...item, [field]: value } : item)));
  const filled = draft.filter(({ title, url }) => title.trim() && url.trim());

  return (
    <form
      className="space-y-3"
      onSubmit={(event) => {
        event.preventDefault();
        save.mutate(filled);
      }}
    >
      {draft.map((item, index) => (
        <div className="grid gap-2 rounded-xl border border-line-soft p-3 sm:grid-cols-[1fr_1.4fr_auto]" key={index}>
          <input aria-label="Título" className="field" maxLength={80} onChange={(event) => update(index, "title", event.target.value)} placeholder="Título" value={item.title} />
          <input aria-label="Endereço" className="field" onChange={(event) => update(index, "url", event.target.value)} placeholder="https://" type="url" value={item.url} />
          <button
            aria-label="Remover link"
            className="btn-secondary"
            onClick={() => setDraft((items) => items.filter((_, position) => position !== index))}
            type="button"
          >
            <Trash2 size={15} />
          </button>
          <input
            aria-label="Descrição"
            className="field sm:col-span-3"
            maxLength={200}
            onChange={(event) => update(index, "description", event.target.value)}
            placeholder="Descrição (opcional)"
            value={item.description}
          />
        </div>
      ))}
      {save.error && <p className="text-xs text-danger">{errorText(save.error)}</p>}
      <div className="flex flex-wrap gap-2">
        <button className="btn-secondary" onClick={() => setDraft((items) => [...items, { title: "", url: "", description: "" }])} type="button">
          <Plus size={15} /> Adicionar link
        </button>
        <button className="btn-primary" disabled={save.isPending} type="submit">
          {save.isPending ? "Salvando…" : "Salvar links"}
        </button>
        <button className="btn-secondary" onClick={onDone} type="button">
          Cancelar
        </button>
      </div>
    </form>
  );
}

/** Integrações → Links: useful links the Super Admin curates for everyone. */
export function LinksPage() {
  const { user } = useAuth();
  const isSuperAdmin = user?.role === "SUPER_ADMIN";
  const [editing, setEditing] = useState(false);
  const links = useQuery({
    queryKey: ["links"],
    queryFn: () => apiRequest<{ links: UsefulLink[] }>("/api/links"),
    retry: false,
  });

  return (
    <div className="mx-auto max-w-[960px] space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold text-fg sm:text-3xl">Links</h1>
        {isSuperAdmin && !editing && links.data && (
          <button className="btn-secondary" onClick={() => setEditing(true)} type="button">
            Editar links
          </button>
        )}
      </header>

      {links.isLoading && <LoadingState label="Carregando links" />}
      {links.error && <ErrorState message="Não foi possível carregar os links." onRetry={() => void links.refetch()} />}
      {links.data &&
        (editing ? (
          <section className="dashboard-card p-4 sm:p-5">
            <LinksEditor links={links.data.links} onDone={() => setEditing(false)} />
          </section>
        ) : links.data.links.length ? (
          <ul className="grid gap-3 sm:grid-cols-2">
            {links.data.links.map((link) => (
              <li key={`${link.url}-${link.title}`}>
                <a
                  className="dashboard-card flex h-full items-start gap-3 rounded-xl p-4 transition hover:border-accent"
                  href={link.url}
                  rel="noopener noreferrer"
                  target="_blank"
                >
                  <Link2 aria-hidden="true" className="mt-0.5 shrink-0 text-accent" size={18} />
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-1.5 font-medium text-fg">
                      {link.title} <ExternalLink aria-hidden="true" className="text-muted" size={13} />
                    </span>
                    {link.description && <span className="mt-1 block text-xs text-muted">{link.description}</span>}
                  </span>
                </a>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted">Nenhum link disponível ainda.</p>
        ))}
    </div>
  );
}
