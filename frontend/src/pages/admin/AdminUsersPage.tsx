import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Ban, Check, LockOpen, Search, Shield, Trash2 } from "lucide-react";

import { AccessAccountButton } from "@/components/AccessAccountButton";
import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { apiRequest, type AdminUser, type Page } from "@/services/api";
import { confirmAction } from "@/lib/confirm";
import { PartnerPermissionsManager } from "@/features/partners/PartnerPermissionsManager";
import { FeeManagementPanel } from "@/features/partners/FeeManagementPanel";

export function AdminUsersPage() {
  const queryClient = useQueryClient();
  const [searchDraft, setSearchDraft] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [selectedPartner, setSelectedPartner] = useState<{ id: string; name: string } | null>(null);
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
  const setAccess = useMutation({
    mutationFn: ({ userId, blocked }: { userId: string; blocked: boolean }) =>
      apiRequest<AdminUser>(`/api/admin/users/${userId}/access`, { method: "PATCH", body: { blocked } }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
  });
  const actionError = [approveUser.error, setAccess.error].find(Boolean);
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
      <FeeManagementPanel />

      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <h2 className="mt-2 text-2xl font-semibold tracking-[-0.045em] text-fg sm:text-3xl">
            Usuários
          </h2>
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
          {actionError && (
            <ErrorState
              message={
                actionError instanceof Error
                  ? actionError.message
                  : "Não foi possível atualizar o usuário."
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
                    <th className="px-4 py-3.5 font-medium">Taxa Flash</th>
                    <th className="px-4 py-3.5 font-medium">Criado em</th>
                    <th className="px-4 py-3.5 font-medium">Último login</th>
                    <th className="px-4 py-3.5 font-medium">Ações</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line text-sm">
                  {users.data.items.map((user) => (
                    <tr
                      key={user.id}
                      className={`hover:bg-surface-raised ${user.hierarchy === "partner" ? "bg-accent/[0.06] shadow-[inset_3px_0_0_var(--color-accent)]" : ""}`}
                    >
                      <td className="px-4 py-4">
                        <p className={`flex flex-wrap items-center gap-2 font-medium ${user.hierarchy === "partner" ? "text-accent" : "text-fg"}`}>
                          {user.full_name}
                          {user.hierarchy === "partner" && (
                            <span className="rounded-md border border-accent/40 bg-accent/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-accent">
                              Sócio
                            </span>
                          )}
                        </p>
                        <p className="mt-1 text-xs text-muted">{user.email}</p>
                      </td>
                      <td className="px-4 py-4 text-fg-2">
                        <span className="block text-fg">{roleLabel(user.role)}</span>
                        <span className="mt-1 block text-xs text-muted">
                          {user.hierarchy === "chief"
                            ? "Chefe"
                            : user.hierarchy === "partner"
                              ? `Sócio de ${user.chief_name ?? "—"}`
                              : user.role === "COLLABORATOR"
                                ? `Colaborador de ${user.workspace_name ?? "—"}`
                                : "Independente"}
                          {user.invited_by_name && ` · convidado por ${user.invited_by_name}`}
                        </span>
                      </td>
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
                          {user.status === "PENDING_APPROVAL" ? "Aguardando aprovação" : user.status === "ACTIVE" ? "Ativo" : "Bloqueado"}
                        </span>
                      </td>
                      <td className="px-4 py-4 text-muted">
                        {user.workspace_name ?? "—"}
                      </td>
                      <td className="px-4 py-4">
                        <TransactionFeeCell user={user} />
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
                          {user.role !== "SUPER_ADMIN" && user.status === "ACTIVE" && (
                            <AccessAccountButton name={user.full_name} userId={user.id} />
                          )}
                          {user.hierarchy === "partner" && (
                            <button
                              className="btn-secondary !min-h-8 text-xs"
                              onClick={() => setSelectedPartner({ id: user.id, name: user.full_name })}
                              type="button"
                            >
                              <Shield size={14} /> Permissões
                            </button>
                          )}
                          {user.role !== "SUPER_ADMIN" && (
                            user.status === "BLOCKED" ? (
                              <button
                                className="inline-flex min-h-8 items-center gap-1.5 rounded-lg border border-line px-2.5 text-xs text-fg-2 hover:bg-surface-raised disabled:opacity-50"
                                disabled={setAccess.isPending}
                                onClick={() => setAccess.mutate({ userId: user.id, blocked: false })}
                                type="button"
                              >
                                <LockOpen size={13} />
                                Desbloquear
                              </button>
                            ) : (
                              <button
                                className="inline-flex min-h-8 items-center gap-1.5 rounded-lg border border-warning/30 px-2.5 text-xs text-warning hover:bg-warning-soft disabled:opacity-50"
                                disabled={setAccess.isPending}
                                onClick={async () => {
                                  if (
                                    await confirmAction(
                                      `Bloquear o acesso de ${user.full_name}? Ele sai da conta, não consegue entrar e os loops das operações dele param de postar até você desbloquear.`,
                                    )
                                  ) {
                                    setAccess.mutate({ userId: user.id, blocked: true });
                                  }
                                }}
                                type="button"
                              >
                                <Ban size={13} />
                                Bloquear
                              </button>
                            )
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

      {selectedPartner && (
        <PartnerPermissionsManager
          userId={selectedPartner.id}
          userName={selectedPartner.name}
          open={!!selectedPartner}
          onClose={() => setSelectedPartner(null)}
        />
      )}
    </div>
  );
}

/** Permissions the Super Admin gives or takes per user: withdrawing and inviting partners. */
function UserPermissions({ user }: { user: AdminUser }) {
  const queryClient = useQueryClient();
  const change = useMutation({
    mutationFn: ({ path, body }: { path: string; body: Record<string, boolean> }) =>
      apiRequest<AdminUser>(`/api/admin/users/${user.id}/${path}`, { method: "PUT", body }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["admin", "users"] }),
  });
  const blocked = Boolean(user.withdrawals_blocked);
  const invites = Boolean(user.can_invite_partners);
  const chip = "inline-flex min-h-8 items-center gap-1.5 rounded-lg border px-2.5 text-xs disabled:opacity-50";
  return (
    <>
      <button
        className={`${chip} ${blocked ? "border-warning/40 bg-warning-soft text-warning" : "border-line text-fg-2 hover:bg-surface-raised"}`}
        disabled={change.isPending}
        onClick={async () => {
          const message = blocked ? `Liberar os saques de ${user.full_name}?` : `Bloquear os saques de ${user.full_name}? Ele não consegue sacar; você ainda consegue sacar por ele.`;
          if (await confirmAction(message)) change.mutate({ path: "withdrawals-blocked", body: { blocked: !blocked } });
        }}
        title="Permissão de saque"
        type="button"
      >
        {blocked ? "Saques bloqueados" : "Saques liberados"}
      </button>
      <button
        className={`${chip} ${invites ? "border-brand/40 bg-brand-soft text-accent" : "border-line text-fg-2 hover:bg-surface-raised"}`}
        disabled={change.isPending}
        onClick={() => change.mutate({ path: "invite-partners", body: { allowed: !invites } })}
        title="Por padrão só você convida sócios"
        type="button"
      >
        {invites ? "Pode convidar sócios" : "Não convida sócios"}
      </button>
    </>
  );
}

const brl = (value: string | number) => Number(value).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

/** The Flash fee each sale of this user's operations pays; the Super Admin sets a special
 * one per user or goes back to the platform default. The Super Admin's own sales never pay. */
function TransactionFeeCell({ user }: { user: AdminUser }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const save = useMutation({
    mutationFn: (fee: string | null) =>
      apiRequest<AdminUser>(`/api/admin/users/${user.id}/transaction-fee`, { method: "PUT", body: { transaction_fee: fee } }),
    onSuccess: () => {
      setEditing(false);
      void queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
      void queryClient.invalidateQueries({ queryKey: ["admin", "summary"] });
    },
  });
  if (user.platform_role === "SUPER_ADMIN") return <span className="text-xs text-muted">Isento</span>;
  const custom = user.transaction_fee !== null && user.transaction_fee !== undefined;
  if (!editing) {
    return (
      <div className="flex items-center gap-2">
        <span className="text-fg">{brl(user.transaction_fee_effective ?? 0)}</span>
        <span className={`rounded-md px-1.5 py-0.5 text-[10px] ${custom ? "bg-brand-soft text-accent" : "bg-well text-muted"}`}>
          {custom ? "especial" : "padrão"}
        </span>
        <button
          className="text-xs text-accent hover:underline"
          onClick={() => {
            setDraft(String(user.transaction_fee_effective ?? "").replace(".", ","));
            setEditing(true);
          }}
          type="button"
        >
          Alterar
        </button>
      </div>
    );
  }
  const value = draft.replace(",", ".").trim();
  const valid = /^\d{1,2}(\.\d{1,2})?$/.test(value) && Number(value) <= 50;
  return (
    <form
      className="flex flex-wrap items-center gap-1.5"
      onSubmit={(event) => {
        event.preventDefault();
        if (valid) save.mutate(Number(value).toFixed(2));
      }}
    >
      <span className="text-xs text-muted">R$</span>
      <input
        aria-label={`Taxa Flash de ${user.full_name}`}
        autoFocus
        className="field h-8 px-2 text-xs"
        style={{ width: "5.5rem" }}
        inputMode="decimal"
        onChange={(event) => setDraft(event.target.value)}
        value={draft}
      />
      <button className="min-h-8 rounded-lg bg-brand px-2.5 text-xs font-medium text-white disabled:opacity-50" disabled={!valid || save.isPending} type="submit">
        Salvar
      </button>
      {custom && (
        <button className="text-xs text-muted hover:text-fg" disabled={save.isPending} onClick={() => save.mutate(null)} type="button">
          Usar padrão
        </button>
      )}
      <button className="text-xs text-muted hover:text-fg" onClick={() => setEditing(false)} type="button">
        Cancelar
      </button>
      {save.error && <span className="w-full text-[11px] text-danger">Não foi possível salvar.</span>}
    </form>
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

function roleLabel(role: string) {
  return role === "SUPER_ADMIN" ? "Super Admin" : role === "OWNER" ? "Dono" : role === "COLLABORATOR" ? "Colaborador" : "Usuário";
}

export function formatDate(value: string) {
  return new Date(value).toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "America/Sao_Paulo",
  });
}
