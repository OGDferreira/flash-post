import { useMemo, useState, type ChangeEvent, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  Clipboard,
  ExternalLink,
  ImagePlus,
  Mail,
  Pencil,
  Plus,
  Save,
  Trash2,
} from "lucide-react";

import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { ApiError, apiRequest } from "@/services/api";

type EmailStatus = "available" | "in_use" | "completed" | "error" | "returned";
type EmailAccount = {
  id: string;
  supplier: string;
  email: string;
  password: string;
  responsible: string | null;
  status: EmailStatus;
  observation: string | null;
  two_factor_code: string;
  two_factor_password: string;
  attachment_url: string | null;
  created_at: string;
  updated_at: string;
};
type EmailForm = Pick<
  EmailAccount,
  "supplier" | "email" | "password" | "two_factor_code" | "two_factor_password"
>;
type EmailsResponse = {
  can_manage: boolean;
  accounts: EmailAccount[];
  counts: {
    total: number;
    available: number;
    in_use: number;
    completed: number;
    error: number;
    returned: number;
  };
};

const emptyForm: EmailForm = {
  supplier: "",
  email: "",
  password: "",
  two_factor_code: "",
  two_factor_password: "",
};
const statuses: { id: EmailStatus; label: string }[] = [
  { id: "available", label: "Disponível" },
  { id: "in_use", label: "Em Uso" },
  { id: "completed", label: "Concluído" },
  { id: "error", label: "Erro" },
  { id: "returned", label: "Retornado" },
];
const nextStatus: Record<EmailStatus, EmailStatus> = {
  available: "in_use",
  in_use: "completed",
  completed: "error",
  error: "returned",
  returned: "available",
};
const statusStyles: Record<EmailStatus, string> = {
  available: "border-[#315843] bg-[#10231a] text-[#a9e5c0]",
  in_use: "border-[#34446f] bg-[#151b2d] text-[#c3ccff]",
  completed: "border-[#4c356a] bg-[#21172f] text-[#d9b8ff]",
  error: "border-[#63343b] bg-[#2b171b] text-[#f1a3ad]",
  returned: "border-[#51422b] bg-[#211b12] text-[#f2d48a]",
};

function errorMessage(error: unknown, fallback: string) {
  return error instanceof ApiError ? error.message : error ? fallback : null;
}

function notify(message: string) {
  window.dispatchEvent(new CustomEvent("flashpost-toast", { detail: message }));
}

function StatusLabel({ status }: { status: EmailStatus }) {
  return statuses.find((item) => item.id === status)?.label ?? status;
}

function SummaryCard({
  label,
  count,
  status,
}: {
  label: string;
  count: number;
  status?: EmailStatus;
}) {
  return (
    <article className="dashboard-card rounded-xl p-4">
      <p className="text-xs text-[#94a3b8]">{label}</p>
      <p
        className={`mt-2 text-2xl font-semibold ${
          status ? statusStyles[status].split(" ").at(-1) : "text-[#f5f7fb]"
        }`}
      >
        {count}
      </p>
    </article>
  );
}

function CopyValue({ value, label }: { value: string; label: string }) {
  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      notify(`${label} copiado`);
    } catch {
      notify(`Não foi possível copiar ${label.toLowerCase()}.`);
    }
  }

  return (
    <button
      className="inline-flex max-w-full items-center gap-1.5 break-all text-left text-[#dbe3f4] hover:text-[#aab7ff]"
      onClick={() => void copy()}
      title={`Copiar ${label}`}
      type="button"
    >
      <span>{value || "—"}</span>
      <Clipboard className="shrink-0 text-[#64748b]" size={12} />
    </button>
  );
}

export function EmailsPage() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<"all" | EmailStatus>("all");
  const [responsibleFilter, setResponsibleFilter] = useState("all");
  const [createForm, setCreateForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<EmailForm>(emptyForm);
  const [importMode, setImportMode] = useState<"file" | "text">("file");
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importText, setImportText] = useState("");
  const [importMessage, setImportMessage] = useState<string | null>(null);
  const [observationDrafts, setObservationDrafts] = useState<Record<string, string>>({});
  const emails = useQuery({
    queryKey: ["emails"],
    queryFn: () => apiRequest<EmailsResponse>("/api/emails"),
    retry: false,
    refetchInterval: 10_000,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["emails"] });
  const createAccount = useMutation({
    mutationFn: (form: EmailForm) =>
      apiRequest<EmailAccount>("/api/emails", { method: "POST", body: form }),
    onSuccess: async () => {
      setCreateForm(emptyForm);
      await refresh();
    },
  });
  const updateAccount = useMutation({
    mutationFn: ({ id, form }: { id: string; form: EmailForm }) =>
      apiRequest<EmailAccount>(`/api/emails/${id}`, { method: "PUT", body: form }),
    onSuccess: async () => {
      setEditingId(null);
      await refresh();
    },
  });
  const importAccounts = useMutation({
    mutationFn: ({
      filename,
      content,
      contentType,
    }: {
      filename: string;
      content: File | string;
      contentType: string;
    }) =>
      apiRequest<{ imported_count: number }>(
        `/api/emails/import?${new URLSearchParams({ filename })}`,
        {
          method: "POST",
          headers: { "Content-Type": contentType },
          body: content,
        },
      ),
    onSuccess: async (result) => {
      setImportFile(null);
      setImportText("");
      setImportMessage(`${result.imported_count} conta(s) importada(s).`);
      await refresh();
    },
  });
  const deleteAccount = useMutation({
    mutationFn: (id: string) =>
      apiRequest<void>(`/api/emails/${id}`, { method: "DELETE" }),
    onSuccess: refresh,
  });
  const changeStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: EmailStatus }) =>
      apiRequest<EmailAccount>(`/api/emails/${id}/status`, {
        method: "PATCH",
        body: { status },
      }),
    onSuccess: refresh,
  });
  const saveObservation = useMutation({
    mutationFn: ({ id, observation }: { id: string; observation: string }) =>
      apiRequest<EmailAccount>(`/api/emails/${id}/observation`, {
        method: "PATCH",
        body: { observation },
      }),
    onSuccess: async (_account, { id }) => {
      setObservationDrafts((drafts) => {
        const next = { ...drafts };
        delete next[id];
        return next;
      });
      await refresh();
    },
  });
  const uploadAttachment = useMutation({
    mutationFn: async ({ id, file }: { id: string; file: File }) => {
      const query = new URLSearchParams({ filename: file.name });
      return apiRequest<{ attachment_url: string }>(
        `/api/emails/${id}/attachment?${query.toString()}`,
        {
          method: "POST",
          headers: { "Content-Type": file.type },
          body: file,
        },
      );
    },
    onSuccess: refresh,
  });

  const accounts = emails.data?.accounts ?? [];
  const responsibles = useMemo(
    () => [...new Set(accounts.map((account) => account.responsible).filter(Boolean))].sort(),
    [accounts],
  );
  const filteredAccounts = accounts.filter(
    (account) =>
      (statusFilter === "all" || account.status === statusFilter) &&
      (responsibleFilter === "all" ||
        (responsibleFilter === "__unassigned__"
          ? account.responsible === null
          : account.responsible === responsibleFilter)),
  );

  function renderFormFields(
    form: EmailForm,
    setForm: (form: EmailForm) => void,
  ) {
    return (
      <>
        <input
          aria-label="Fornecedor"
          className="collaborator-input min-w-28"
          maxLength={120}
          onChange={(event) => setForm({ ...form, supplier: event.target.value })}
          placeholder="Fornecedor"
          required
          value={form.supplier}
        />
        <input
          aria-label="E-mail"
          autoComplete="off"
          className="collaborator-input min-w-48"
          onChange={(event) => setForm({ ...form, email: event.target.value })}
          placeholder="E-mail"
          required
          type="email"
          value={form.email}
        />
        <input
          aria-label="Senha"
          autoComplete="new-password"
          className="collaborator-input min-w-36"
          onChange={(event) => setForm({ ...form, password: event.target.value })}
          placeholder="Senha"
          required
          value={form.password}
        />
        <input
          aria-label="Código 2FA"
          className="collaborator-input min-w-36"
          onChange={(event) => setForm({ ...form, two_factor_code: event.target.value })}
          placeholder="Código 2FA"
          required
          value={form.two_factor_code}
        />
        <input
          aria-label="Senha do 2FA"
          autoComplete="new-password"
          className="collaborator-input min-w-36"
          onChange={(event) => setForm({ ...form, two_factor_password: event.target.value })}
          placeholder="Senha do 2FA"
          value={form.two_factor_password}
        />
      </>
    );
  }

  function handleAttachment(id: string, event: ChangeEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0];
    event.currentTarget.value = "";
    if (!file) return;
    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
      notify("Use uma imagem JPEG, PNG ou WebP.");
      return;
    }
    uploadAttachment.mutate({ id, file });
  }

  if (emails.isLoading) return <LoadingState label="Carregando controle de e-mails" />;
  if (emails.error || !emails.data) {
    return <ErrorState message={errorMessage(emails.error, "Não foi possível carregar os e-mails.") ?? ""} />;
  }

  const errors = [
    errorMessage(createAccount.error, "Não foi possível adicionar a conta."),
    errorMessage(updateAccount.error, "Não foi possível atualizar a conta."),
    errorMessage(deleteAccount.error, "Não foi possível excluir a conta."),
    errorMessage(changeStatus.error, "Não foi possível atualizar o status."),
    errorMessage(saveObservation.error, "Não foi possível salvar a observação."),
    errorMessage(uploadAttachment.error, "Não foi possível enviar o anexo."),
    errorMessage(importAccounts.error, "Não foi possível importar a planilha."),
  ].filter(Boolean);

  return (
    <div className="mx-auto max-w-[1600px] space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-[#8295ff]">
            Workspace
          </p>
          <h1 className="mt-2 flex items-center gap-2 text-2xl font-semibold text-[#f5f7fb] sm:text-3xl">
            <Mail className="text-[#8295ff]" size={25} />
            Controle de E-mails
          </h1>
          <p className="mt-2 text-sm text-[#94a3b8]">
            Contas, responsáveis, status e registros de erro do workspace.
          </p>
        </div>
        <a
          className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-[#34446f] bg-[#11182d] px-4 text-sm font-semibold text-[#c3ccff] hover:bg-[#151b2d]"
          href="https://2fagen.com/"
          rel="noopener noreferrer"
          target="_blank"
        >
          Gerador 2FA <ExternalLink size={14} />
        </a>
      </header>

      <section aria-label="Resumo de status" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <SummaryCard count={emails.data.counts.total} label="Total" />
        <SummaryCard count={emails.data.counts.available} label="Disponível" status="available" />
        <SummaryCard count={emails.data.counts.in_use} label="Em Uso" status="in_use" />
        <SummaryCard count={emails.data.counts.completed} label="Concluído" status="completed" />
        <SummaryCard count={emails.data.counts.error} label="Erro" status="error" />
        <SummaryCard count={emails.data.counts.returned} label="Retornado" status="returned" />
      </section>

      {errors.map((error) => (
        <ErrorState key={error} message={error ?? ""} />
      ))}

      {emails.data.can_manage && (
        <details className="dashboard-card rounded-xl p-5">
          <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-semibold text-[#edf0f8]">
            <Plus className="text-[#8295ff]" size={16} />
            Adicionar conta de e-mail
          </summary>
          <form
            className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
            onSubmit={(event: FormEvent) => {
              event.preventDefault();
              createAccount.mutate(createForm);
            }}
          >
            {renderFormFields(createForm, setCreateForm)}
            <button
              className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-[#536dfe] px-4 text-sm font-semibold text-white disabled:opacity-50 sm:col-span-2 xl:col-span-4"
              disabled={createAccount.isPending}
              type="submit"
            >
              <Plus size={15} />
              {createAccount.isPending ? "Salvando..." : "Adicionar"}
            </button>
          </form>
        </details>
      )}

      {emails.data.can_manage && (
        <details className="dashboard-card rounded-xl p-5">
          <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-semibold text-[#edf0f8]">
            <Plus className="text-[#8295ff]" size={16} />
            Importar contas por arquivo ou texto
          </summary>
          <div className="mt-4 space-y-3">
            <div aria-label="Forma de importar" className="flex flex-wrap gap-2">
              <button
                aria-pressed={importMode === "file"}
                className={`min-h-9 rounded-lg border px-3 text-sm font-medium ${
                  importMode === "file"
                    ? "border-[#536dfe] bg-[#18234a] text-[#d8ddff]"
                    : "border-[#34446f] text-[#94a3b8]"
                }`}
                onClick={() => setImportMode("file")}
                type="button"
              >
                Enviar arquivo TXT
              </button>
              <button
                aria-pressed={importMode === "text"}
                className={`min-h-9 rounded-lg border px-3 text-sm font-medium ${
                  importMode === "text"
                    ? "border-[#536dfe] bg-[#18234a] text-[#d8ddff]"
                    : "border-[#34446f] text-[#94a3b8]"
                }`}
                onClick={() => setImportMode("text")}
                type="button"
              >
                Colar ou escrever texto
              </button>
            </div>
            {importMode === "file" ? (
              <div className="flex flex-wrap items-center gap-3">
                <input
                  accept=".txt,.csv,.xlsx"
                  aria-label="Arquivo com contas"
                  className="collaborator-input min-w-56"
                  key={importFile?.name ?? "no-file"}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => {
                    setImportFile(event.currentTarget.files?.[0] ?? null);
                    setImportMessage(null);
                  }}
                  type="file"
                />
                {importFile && (
                  <span className="text-xs text-[#94a3b8]">{importFile.name}</span>
                )}
              </div>
            ) : (
              <textarea
                aria-label="Texto das contas"
                className="collaborator-input min-h-36 w-full resize-y font-mono text-xs"
                onChange={(event) => {
                  setImportText(event.target.value);
                  setImportMessage(null);
                }}
                placeholder={"Fornecedor : email@exemplo.com : senha : codigo 2FA : senha 2FA\nFornecedor : email2@exemplo.com : senha : codigo 2FA : "}
                value={importText}
              />
            )}
            <p className="text-xs text-[#94a3b8]">
              Uma conta por linha, nesta ordem: fornecedor : e-mail : senha : código 2FA : senha 2FA.
              Também aceitamos os campos separados por tabulação. A senha do 2FA pode ficar vazia.
            </p>
            <button
              className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-[#536dfe] px-4 text-sm font-semibold text-white disabled:opacity-50"
              disabled={
                importAccounts.isPending ||
                (importMode === "file" ? !importFile : !importText.trim())
              }
              onClick={() => {
                if (importMode === "file" && importFile) {
                  importAccounts.mutate({
                    filename: importFile.name,
                    content: importFile,
                    contentType: importFile.type || "text/plain",
                  });
                } else if (importMode === "text" && importText.trim()) {
                  importAccounts.mutate({
                    filename: "contas.txt",
                    content: importText,
                    contentType: "text/plain; charset=utf-8",
                  });
                }
              }}
              type="button"
            >
              {importAccounts.isPending ? "Importando..." : "Importar"}
            </button>
            {importMessage && <p className="text-sm text-[#a9e5c0]">{importMessage}</p>}
          </div>
        </details>
      )}

      <section className="dashboard-card space-y-4 rounded-xl p-4 sm:p-5">
        <div className="flex flex-wrap items-center gap-3">
          <label className="grid gap-1 text-xs text-[#94a3b8]">
            Filtrar por Status
            <select
              className="collaborator-input min-w-44"
              onChange={(event) => setStatusFilter(event.target.value as "all" | EmailStatus)}
              value={statusFilter}
            >
              <option value="all">Todos os status</option>
              {statuses.map(({ id, label }) => (
                <option key={id} value={id}>{label}</option>
              ))}
            </select>
          </label>
          <label className="grid gap-1 text-xs text-[#94a3b8]">
            Filtrar por Responsável
            <select
              className="collaborator-input min-w-44"
              onChange={(event) => setResponsibleFilter(event.target.value)}
              value={responsibleFilter}
            >
              <option value="all">Todos os responsáveis</option>
              {accounts.some((account) => !account.responsible) && (
                <option value="__unassigned__">Sem responsável</option>
              )}
              {responsibles.map((responsible) => (
                <option key={responsible} value={responsible ?? ""}>{responsible}</option>
              ))}
            </select>
          </label>
          <span className="ml-auto text-xs text-[#78839b]">
            {filteredAccounts.length} de {accounts.length} conta(s)
          </span>
        </div>

        {filteredAccounts.length === 0 ? (
          <EmptyState message="Nenhuma conta corresponde aos filtros." />
        ) : (
          <div className="overflow-x-auto rounded-lg border border-[#202838]">
            <table className="w-full min-w-[1500px] border-collapse text-left text-xs">
              <thead className="bg-[#11151d] text-[10px] uppercase tracking-[0.1em] text-[#94a3b8]">
                <tr>
                  <th className="px-3 py-3">Fornecedor</th>
                  <th className="px-3 py-3">E-mail</th>
                  <th className="px-3 py-3">Senha</th>
                  <th className="px-3 py-3">Responsável</th>
                  <th className="px-3 py-3">Status</th>
                  <th className="px-3 py-3">Observações</th>
                  <th className="px-3 py-3">Código 2FA</th>
                  <th className="px-3 py-3">Senha do 2FA</th>
                  <th className="px-3 py-3">Anexo/Foto (erro)</th>
                  {emails.data.can_manage && <th className="px-3 py-3">Ações</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-[#202838]">
                {filteredAccounts.map((account) => (
                  <tr className="align-top hover:bg-[#10141b]" key={account.id}>
                    {editingId === account.id ? (
                      <>
                        <td className="px-2 py-2">
                          <input aria-label="Fornecedor" className="collaborator-input min-w-28" value={editForm.supplier} onChange={(event) => setEditForm({ ...editForm, supplier: event.target.value })} />
                        </td>
                        <td className="px-2 py-2">
                          <input aria-label="E-mail" className="collaborator-input min-w-48" type="email" value={editForm.email} onChange={(event) => setEditForm({ ...editForm, email: event.target.value })} />
                        </td>
                        <td className="px-2 py-2">
                          <input aria-label="Senha" className="collaborator-input min-w-36" value={editForm.password} onChange={(event) => setEditForm({ ...editForm, password: event.target.value })} />
                        </td>
                        <td className="px-3 py-3 text-[#94a3b8]">{account.responsible ?? "—"}</td>
                        <td className="px-3 py-3"><span className={`rounded-full border px-2 py-1 ${statusStyles[account.status]}`}><StatusLabel status={account.status} /></span></td>
                        <td className="px-3 py-3 text-[#94a3b8]">{account.observation || "—"}</td>
                        <td className="px-2 py-2">
                          <input aria-label="Código 2FA" className="collaborator-input min-w-36" value={editForm.two_factor_code} onChange={(event) => setEditForm({ ...editForm, two_factor_code: event.target.value })} />
                        </td>
                        <td className="px-2 py-2">
                          <input aria-label="Senha do 2FA" className="collaborator-input min-w-36" value={editForm.two_factor_password} onChange={(event) => setEditForm({ ...editForm, two_factor_password: event.target.value })} />
                        </td>
                        <td className="px-3 py-3">{account.attachment_url ? <a className="text-[#aab7ff]" href={account.attachment_url} rel="noreferrer" target="_blank">Ver imagem</a> : "—"}</td>
                        <td className="px-2 py-2">
                          <div className="flex gap-2">
                            <button aria-label="Salvar edição" className="rounded border border-[#315843] p-2 text-[#a9e5c0]" disabled={updateAccount.isPending} onClick={() => updateAccount.mutate({ id: account.id, form: editForm })} type="button"><Save size={14} /></button>
                            <button aria-label="Cancelar edição" className="rounded border border-[#27334a] p-2 text-[#94a3b8]" onClick={() => setEditingId(null)} type="button">×</button>
                          </div>
                        </td>
                      </>
                    ) : (
                      <>
                        <td className="px-3 py-3 font-medium text-[#cbd5e1]">{account.supplier}</td>
                        <td className="px-3 py-3"><CopyValue label="E-mail" value={account.email} /></td>
                        <td className="px-3 py-3"><CopyValue label="Senha" value={account.password} /></td>
                        <td className="px-3 py-3 text-[#cbd5e1]">{account.responsible ?? "—"}</td>
                        <td className="px-3 py-3">
                          <button
                            className={`rounded-full border px-2.5 py-1 font-medium hover:brightness-125 ${statusStyles[account.status]}`}
                            disabled={changeStatus.isPending}
                            onClick={() => changeStatus.mutate({ id: account.id, status: nextStatus[account.status] })}
                            title={`Avançar para ${statuses.find(({ id }) => id === nextStatus[account.status])?.label}`}
                            type="button"
                          >
                            <StatusLabel status={account.status} />
                          </button>
                        </td>
                        <td className="min-w-56 px-2 py-2">
                          <textarea
                            aria-label={`Observações de ${account.email}`}
                            className="collaborator-input min-h-16 w-full resize-y"
                            maxLength={4000}
                            onChange={(event) => setObservationDrafts({ ...observationDrafts, [account.id]: event.target.value })}
                            placeholder="Adicionar observação"
                            value={observationDrafts[account.id] ?? account.observation ?? ""}
                          />
                          {observationDrafts[account.id] !== undefined && (
                            <button
                              className="mt-1 inline-flex items-center gap-1 rounded border border-[#34446f] px-2 py-1 text-[10px] text-[#c3ccff]"
                              disabled={saveObservation.isPending}
                              onClick={() => saveObservation.mutate({ id: account.id, observation: observationDrafts[account.id] })}
                              type="button"
                            >
                              <Check size={12} /> Salvar observação
                            </button>
                          )}
                        </td>
                        <td className="px-3 py-3"><CopyValue label="Código 2FA" value={account.two_factor_code} /></td>
                        <td className="px-3 py-3"><CopyValue label="Senha do 2FA" value={account.two_factor_password} /></td>
                        <td className="px-3 py-3">
                          <div className="flex min-w-36 items-center gap-2">
                            {account.attachment_url && (
                              <a href={account.attachment_url} rel="noreferrer" target="_blank">
                                <img alt="Anexo de erro" className="size-10 rounded border border-[#27334a] object-cover" src={account.attachment_url} />
                              </a>
                            )}
                            <label className="inline-flex cursor-pointer items-center gap-1 rounded border border-[#27334a] px-2 py-2 text-[#aab7ff] hover:bg-[#151b2d]">
                              <ImagePlus size={14} />
                              <span>{account.attachment_url ? "Trocar" : "Anexar"}</span>
                              <input accept="image/jpeg,image/png,image/webp" className="sr-only" disabled={uploadAttachment.isPending} onChange={(event) => handleAttachment(account.id, event)} type="file" />
                            </label>
                          </div>
                        </td>
                        {emails.data.can_manage && (
                          <td className="px-3 py-3">
                            <div className="flex gap-2">
                              <button
                                aria-label={`Editar ${account.email}`}
                                className="rounded border border-[#27334a] p-2 text-[#aab7ff] hover:bg-[#151b2d]"
                                onClick={() => {
                                  setEditingId(account.id);
                                  setEditForm({
                                    supplier: account.supplier,
                                    email: account.email,
                                    password: account.password,
                                    two_factor_code: account.two_factor_code,
                                    two_factor_password: account.two_factor_password,
                                  });
                                }}
                                type="button"
                              >
                                <Pencil size={14} />
                              </button>
                              <button
                                aria-label={`Excluir ${account.email}`}
                                className="rounded border border-[#5a3037] p-2 text-[#f1a3ad] hover:bg-[#241216]"
                                onClick={() => {
                                  if (window.confirm(`Excluir a conta ${account.email}?`)) deleteAccount.mutate(account.id);
                                }}
                                type="button"
                              >
                                <Trash2 size={14} />
                              </button>
                            </div>
                          </td>
                        )}
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
