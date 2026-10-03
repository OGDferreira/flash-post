import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";

import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { apiRequest, type AdminUser, type Page } from "@/services/api";

export function AdminUsersPage() {
  const [searchDraft, setSearchDraft] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const pageSize = 20;
  const users = useQuery({
    queryKey: ["admin", "users", search, page],
    queryFn: () =>
      apiRequest<Page<AdminUser>>(
        `/api/admin/users?page=${page}&page_size=${pageSize}&q=${encodeURIComponent(search)}`,
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
            Usuários
          </h2>
          <p className="mt-2 text-sm text-[#94a3b8]">
            Contas da plataforma, função e workspace associado.
          </p>
        </div>
        <form onSubmit={submitSearch} className="flex w-full gap-2 sm:max-w-sm">
          <label className="relative min-w-0 flex-1">
            <span className="sr-only">Buscar usuários</span>
            <Search
              size={16}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-[#64748b]"
            />
            <input
              value={searchDraft}
              onChange={(event) => setSearchDraft(event.target.value)}
              placeholder="Nome ou e-mail"
              maxLength={120}
              className="h-10 w-full rounded-lg border border-[#27334a] bg-[#0d1015] pl-9 pr-3 text-sm text-[#f5f7fb] outline-none focus:border-[#536dfe]"
            />
          </label>
          <button className="h-10 rounded-lg border border-[#27334a] bg-[#10141b] px-4 text-sm text-[#c7cfdd] hover:bg-[#171e31]">
            Buscar
          </button>
        </form>
      </div>

      {users.isLoading ? (
        <LoadingState label="Carregando usuários" />
      ) : users.error || !users.data ? (
        <ErrorState message="Não foi possível carregar a lista de usuários." />
      ) : users.data.items.length === 0 ? (
        <EmptyState message="Nenhum usuário encontrado." />
      ) : (
        <>
          <div className="overflow-hidden rounded-xl border border-[#202838] bg-[#0d1015]">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] border-collapse text-left">
                <thead className="border-b border-[#202838] bg-[#0a0d11] text-[11px] uppercase tracking-[0.12em] text-[#64748b]">
                  <tr>
                    <th className="px-5 py-3.5 font-medium">Usuário</th>
                    <th className="px-5 py-3.5 font-medium">Role</th>
                    <th className="px-5 py-3.5 font-medium">Status</th>
                    <th className="px-5 py-3.5 font-medium">Workspace</th>
                    <th className="px-5 py-3.5 font-medium">Criado em</th>
                    <th className="px-5 py-3.5 font-medium">Último login</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#1b2330] text-sm">
                  {users.data.items.map((user) => (
                    <tr key={user.id} className="hover:bg-[#10141b]">
                      <td className="px-5 py-4">
                        <p className="font-medium text-[#e6eaf2]">{user.full_name}</p>
                        <p className="mt-1 text-xs text-[#64748b]">{user.email}</p>
                      </td>
                      <td className="px-5 py-4 text-[#c7cfdd]">{user.role}</td>
                      <td className="px-5 py-4">
                        <span className="rounded-md border border-[#1d3b37] bg-[#0c1715] px-2 py-1 text-xs text-[#9de6d1]">
                          {user.status}
                        </span>
                      </td>
                      <td className="px-5 py-4 text-[#94a3b8]">
                        {user.workspace_name ?? "—"}
                      </td>
                      <td className="px-5 py-4 text-[#94a3b8]">
                        {formatDate(user.created_at)}
                      </td>
                      <td className="px-5 py-4 text-[#94a3b8]">
                        {user.last_login_at ? formatDate(user.last_login_at) : "Nunca"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <Pagination
            page={users.data.page}
            pageSize={users.data.page_size}
            total={users.data.total}
            onChange={setPage}
          />
        </>
      )}
    </div>
  );
}

export function Pagination({
  page,
  pageSize,
  total,
  onChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  onChange: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="flex flex-col gap-3 text-xs text-[#64748b] sm:flex-row sm:items-center sm:justify-between">
      <span>
        {total === 0 ? "0 resultados" : `${(page - 1) * pageSize + 1}–${Math.min(page * pageSize, total)} de ${total}`}
      </span>
      <div className="flex gap-2">
        <button
          onClick={() => onChange(Math.max(1, page - 1))}
          disabled={page <= 1}
          className="min-h-9 rounded-lg border border-[#27334a] px-3 text-[#c7cfdd] hover:bg-[#10141b] disabled:opacity-40"
        >
          Anterior
        </button>
        <span className="flex min-h-9 items-center px-2">
          Página {page} de {pages}
        </span>
        <button
          onClick={() => onChange(Math.min(pages, page + 1))}
          disabled={page >= pages}
          className="min-h-9 rounded-lg border border-[#27334a] px-3 text-[#c7cfdd] hover:bg-[#10141b] disabled:opacity-40"
        >
          Próxima
        </button>
      </div>
    </div>
  );
}

export function formatDate(value: string) {
  return new Date(value).toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "America/Sao_Paulo",
  });
}
