import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Search, Trash2 } from "lucide-react";

import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { apiRequest, type AdminUser, type Page } from "@/services/api";
import { confirmAction } from "@/lib/confirm";

export function AdminUsersPage() {
  const queryClient = useQueryClient();
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
  const approveUser = useMutation({
    mutationFn: (userId: string) =>
      apiRequest<AdminUser>(`/api/admin/users/${userId}/approve`, { method: "POST" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
  });
  const deleteUser = useMutation({
    mutationFn: (userId: string) =>
      apiRequest<void>(`/api/admin/users/${userId}`, { method: "DELETE" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
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
            Usuários
          </h2>
          <p className="mt-2 text-sm text-muted">
            Contas da plataforma, função e workspace associado.
          </p>
        </div>
        <form onSubmit={submitSearch} className="flex w-full gap-2 sm:max-w-sm">
          <label className="relative min-w-0 flex-1">
            <span className="sr-only">Buscar usuários</span>
            <Search
              size={16}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-muted"
            />
            <input
              value={searchDraft}
              onChange={(event) => setSearchDraft(event.target.value)}
              placeholder="Nome ou e-mail"
              maxLength={120}
              className="h-10 w-full rounded-lg border border-line bg-surface pl-9 pr-3 text-sm text-fg outline-none focus:border-brand"
            />
          </label>
          <button className="h-10 rounded-lg border border-line bg-surface-raised px-4 text-sm text-fg-2 hover:bg-brand-soft">
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
          {approveUser.error && (
            <ErrorState
              message={
                approveUser.error instanceof Error
                  ? approveUser.error.message
                  : "Não foi possível aprovar o usuário."
              }
            />
          )}
          {deleteUser.error && (
            <ErrorState
              message={
                deleteUser.error instanceof Error
                  ? deleteUser.error.message
                  : "Não foi possível excluir o usuário."
              }
            />
          )}
          <div className="overflow-hidden rounded-xl border border-line-soft bg-surface">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[920px] border-collapse text-left">
                <thead className="border-b border-line-soft bg-well text-[11px] uppercase tracking-[0.12em] text-muted">
                  <tr>
                    <th className="px-4 py-3.5 font-medium">Usuário</th>
                    <th className="px-4 py-3.5 font-medium">Role</th>
                    <th className="px-4 py-3.5 font-medium">Status</th>
                    <th className="px-4 py-3.5 font-medium">Workspace</th>
                    <th className="px-4 py-3.5 font-medium">Criado em</th>
                    <th className="px-4 py-3.5 font-medium">Último login</th>
                    <th className="px-4 py-3.5 font-medium">Ações</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line text-sm">
                  {users.data.items.map((user) => (
                    <tr key={user.id} className="hover:bg-surface-raised">
                      <td className="px-4 py-4">
                        <p className="font-medium text-fg">{user.full_name}</p>
                        <p className="mt-1 text-xs text-muted">{user.email}</p>
                      </td>
                      <td className="px-4 py-4 text-fg-2">{user.role}</td>
                      <td className="px-4 py-4">
                        <span
                          className={`rounded-md border px-2 py-1 text-xs ${
                            user.status === "PENDING_APPROVAL"
                              ? "border-warning/30 bg-warning-soft text-warning"
                              : user.status === "ACTIVE"
                                ? "border-success/30 bg-success-soft text-success"
                                : "border-danger/30 bg-danger-soft text-danger"
                          }`}
                        >
                          {user.status === "PENDING_APPROVAL" ? "Aguardando aprovação" : user.status}
                        </span>
                      </td>
                      <td className="px-4 py-4 text-muted">
                        {user.workspace_name ?? "—"}
                      </td>
                      <td className="px-4 py-4 text-muted">
                        {formatDate(user.created_at)}
                      </td>
                      <td className="px-4 py-4 text-muted">
                        {user.last_login_at ? formatDate(user.last_login_at) : "Nunca"}
                      </td>
                      <td className="px-4 py-4">
                        <div className="flex flex-wrap items-center gap-2">
                          {user.is_approved ? (
                            <span className="inline-flex items-center gap-1 text-xs text-success">
                              <Check size={14} /> Aprovado
                            </span>
                          ) : (
                            <button
                              className="min-h-8 rounded-lg bg-brand px-3 text-xs font-medium text-white hover:bg-brand disabled:opacity-50"
                              disabled={approveUser.isPending}
                              onClick={() => approveUser.mutate(user.id)}
                              type="button"
                            >
                              Aprovar acesso
                            </button>
                          )}
                          {user.role !== "SUPER_ADMIN" && (
                            <button
                              aria-label={`Excluir ${user.full_name}`}
                              className="inline-flex min-h-8 items-center gap-1.5 rounded-lg border border-danger/30 px-2.5 text-xs text-danger hover:bg-danger-soft disabled:opacity-50"
                              disabled={deleteUser.isPending}
                              onClick={async () => {
                                if (
                                  await confirmAction(
                                    `Excluir permanentemente o usuário ${user.full_name}? A ação não pode ser desfeita. Contas administradoras e donos de workspace são protegidos.`,
                                  )
                                ) {
                                  deleteUser.mutate(user.id);
                                }
                              }}
                              type="button"
                            >
                              <Trash2 size={13} />
                              Excluir
                            </button>
                          )}
                        </div>
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
    <div className="flex flex-col gap-3 text-xs text-muted sm:flex-row sm:items-center sm:justify-between">
      <span>
        {total === 0 ? "0 resultados" : `${(page - 1) * pageSize + 1}–${Math.min(page * pageSize, total)} de ${total}`}
      </span>
      <div className="flex gap-2">
        <button
          onClick={() => onChange(Math.max(1, page - 1))}
          disabled={page <= 1}
          className="min-h-9 rounded-lg border border-line px-3 text-fg-2 hover:bg-surface-raised disabled:opacity-40"
        >
          Anterior
        </button>
        <span className="flex min-h-9 items-center px-2">
          Página {page} de {pages}
        </span>
        <button
          onClick={() => onChange(Math.min(pages, page + 1))}
          disabled={page >= pages}
          className="min-h-9 rounded-lg border border-line px-3 text-fg-2 hover:bg-surface-raised disabled:opacity-40"
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
