import { useState, type FormEvent } from "react";
import { AccessAccountButton } from "@/components/AccessAccountButton";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";

import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import {
  apiRequest,
  type AdminWorkspace,
  type Page,
} from "@/services/api";
import { Pagination } from "@/pages/admin/AdminUsersPage";

export function AdminWorkspacesPage() {
  const [searchDraft, setSearchDraft] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const pageSize = 20;
  const workspaces = useQuery({
    queryKey: ["admin", "workspaces", search, page],
    queryFn: () =>
      apiRequest<Page<AdminWorkspace>>(
        `/api/admin/workspaces?page=${page}&page_size=${pageSize}&q=${encodeURIComponent(search)}`,
      ),
  });

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSearch(searchDraft.trim());
    setPage(1);
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-accent">
            Administração
          </p>
          <h2 className="mt-2 text-2xl font-semibold tracking-[-0.045em] text-fg sm:text-3xl">
            Workspaces
          </h2>
          <p className="mt-2 text-sm text-muted">
            Espaços de trabalho e seus respectivos owners.
          </p>
        </div>
        <form onSubmit={submitSearch} className="flex w-full gap-2 sm:max-w-sm">
          <label className="relative min-w-0 flex-1">
            <span className="sr-only">Buscar workspaces</span>
            <Search
              size={16}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-muted"
            />
            <input
              value={searchDraft}
              onChange={(event) => setSearchDraft(event.target.value)}
              placeholder="Workspace ou owner"
              maxLength={120}
              className="h-10 w-full rounded-lg border border-line bg-surface pl-9 pr-3 text-sm text-fg outline-none focus:border-brand"
            />
          </label>
          <button className="h-10 rounded-lg border border-line bg-surface-raised px-4 text-sm text-fg-2 hover:bg-brand-soft">
            Buscar
          </button>
        </form>
      </div>

      {workspaces.isLoading ? (
        <LoadingState label="Carregando workspaces" />
      ) : workspaces.error || !workspaces.data ? (
        <ErrorState message="Não foi possível carregar a lista de workspaces." />
      ) : workspaces.data.items.length === 0 ? (
        <EmptyState message="Nenhum workspace encontrado." />
      ) : (
        <>
          <div className="overflow-hidden rounded-xl border border-line-soft bg-surface">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[1050px] border-collapse text-left">
                <thead className="border-b border-line-soft bg-well text-[11px] uppercase tracking-[0.12em] text-muted">
                  <tr>
                    <th className="px-4 py-3.5 font-medium">Chefe autorizado</th>
                    <th className="px-4 py-3.5 font-medium">Workspace</th>
                    <th className="px-4 py-3.5 font-medium">Contas conectadas</th>
                    <th className="px-4 py-3.5 font-medium">Contas com erro</th>
                    <th className="px-4 py-3.5 font-medium">Posts em execução</th>
                    <th className="px-4 py-3.5 font-medium">Colaboradores</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line text-sm">
                  {workspaces.data.items.map((workspace) => (
                    <tr key={workspace.id} className="hover:bg-surface-raised">
                      <td className="px-4 py-4">
                        <p className="font-medium text-fg">{workspace.owner_name}</p>
                        <p className="mt-1 text-xs text-muted">{workspace.owner_email}</p>
                        {workspace.owner_id && <AccessAccountButton className="mt-2" name={workspace.owner_name} userId={workspace.owner_id} />}
                      </td>
                      <td className="px-4 py-4 text-muted">
                        <p className="text-fg-2">{workspace.name}</p>
                        <p className="mt-1 text-xs text-muted">{workspace.slug}</p>
                        <p className="mt-1 text-xs text-muted">{workspace.members_count} membros · {workspace.status}</p>
                      </td>
                      <td className="px-4 py-4 text-fg-2">{workspace.connected_accounts}</td>
                      <td className="px-4 py-4 text-warning">{workspace.errored_accounts}</td>
                      <td className="px-4 py-4 text-fg-2">{workspace.active_posts}</td>
                      <td className="px-4 py-4">
                        {workspace.collaborators.length ? (
                          <ul className="space-y-1 text-xs text-fg-2">
                            {workspace.collaborators.map((person) => (
                              <li key={person.id}>
                                {person.full_name} <span className="text-muted">({person.email})</span>
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <span className="text-xs text-muted">Nenhum</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <Pagination
            page={workspaces.data.page}
            pageSize={workspaces.data.page_size}
            total={workspaces.data.total}
            onChange={setPage}
          />
        </>
      )}
    </div>
  );
}
