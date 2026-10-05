import { useState, type FormEvent } from "react";
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
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-[#7186ff]">
            Administração
          </p>
          <h2 className="mt-2 text-2xl font-semibold tracking-[-0.045em] text-[#f5f7fb] sm:text-3xl">
            Workspaces
          </h2>
          <p className="mt-2 text-sm text-[#94a3b8]">
            Espaços de trabalho e seus respectivos owners.
          </p>
        </div>
        <form onSubmit={submitSearch} className="flex w-full gap-2 sm:max-w-sm">
          <label className="relative min-w-0 flex-1">
            <span className="sr-only">Buscar workspaces</span>
            <Search
              size={16}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-[#64748b]"
            />
            <input
              value={searchDraft}
              onChange={(event) => setSearchDraft(event.target.value)}
              placeholder="Workspace ou owner"
              maxLength={120}
              className="h-10 w-full rounded-lg border border-[#27334a] bg-[#0d1015] pl-9 pr-3 text-sm text-[#f5f7fb] outline-none focus:border-[#536dfe]"
            />
          </label>
          <button className="h-10 rounded-lg border border-[#27334a] bg-[#10141b] px-4 text-sm text-[#c7cfdd] hover:bg-[#171e31]">
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
          <div className="overflow-hidden rounded-xl border border-[#202838] bg-[#0d1015]">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[1050px] border-collapse text-left">
                <thead className="border-b border-[#202838] bg-[#0a0d11] text-[11px] uppercase tracking-[0.12em] text-[#64748b]">
                  <tr>
                    <th className="px-5 py-3.5 font-medium">Chefe autorizado</th>
                    <th className="px-5 py-3.5 font-medium">Workspace</th>
                    <th className="px-5 py-3.5 font-medium">Contas conectadas</th>
                    <th className="px-5 py-3.5 font-medium">Contas com erro</th>
                    <th className="px-5 py-3.5 font-medium">Posts em execução</th>
                    <th className="px-5 py-3.5 font-medium">Colaboradores</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#1b2330] text-sm">
                  {workspaces.data.items.map((workspace) => (
                    <tr key={workspace.id} className="hover:bg-[#10141b]">
                      <td className="px-5 py-4">
                        <p className="font-medium text-[#e6eaf2]">{workspace.owner_name}</p>
                        <p className="mt-1 text-xs text-[#64748b]">{workspace.owner_email}</p>
                      </td>
                      <td className="px-5 py-4 text-[#94a3b8]">
                        <p className="text-[#c7cfdd]">{workspace.name}</p>
                        <p className="mt-1 text-xs text-[#64748b]">{workspace.slug}</p>
                        <p className="mt-1 text-xs text-[#64748b]">{workspace.members_count} membros · {workspace.status}</p>
                      </td>
                      <td className="px-5 py-4 text-[#c7cfdd]">{workspace.connected_accounts}</td>
                      <td className="px-5 py-4 text-[#f2d48a]">{workspace.errored_accounts}</td>
                      <td className="px-5 py-4 text-[#c7cfdd]">{workspace.active_posts}</td>
                      <td className="px-5 py-4">
                        {workspace.collaborators.length ? (
                          <ul className="space-y-1 text-xs text-[#c7cfdd]">
                            {workspace.collaborators.map((person) => (
                              <li key={person.id}>
                                {person.full_name} <span className="text-[#64748b]">({person.email})</span>
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <span className="text-xs text-[#64748b]">Nenhum</span>
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
