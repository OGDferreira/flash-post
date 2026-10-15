import { useMemo, useState, type ChangeEvent, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createPortal } from "react-dom";
import {
  Check,
  ExternalLink,
  ImagePlus,
  Mail,
  Pencil,
  Plus,
  Save,
  Trash2,
} from "lucide-react";

import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { apiRequest } from "@/services/api";
import { confirmAction } from "@/lib/confirm";
import { type EmailStatus, type EmailAccount, type EmailForm, type EmailsResponse, emptyForm, statuses, nextStatus, statusStyles, errorMessage, notify, StatusLabel, SummaryCard, CopyValue } from "@/pages/emails/emailShared";

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
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [batchFilter, setBatchFilter] = useState("all");
  const [textModalOpen, setTextModalOpen] = useState(false);
  const [supplierPromptOpen, setSupplierPromptOpen] = useState(false);
  const [bulkSupplier, setBulkSupplier] = useState("");
  const emails = useQuery({
    queryKey: ["emails"],
    queryFn: () => apiRequest<EmailsResponse>("/api/emails"),
    retry: false,
    refetchInterval: 60_000,
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
      supplier,
    }: {
      filename: string;
      content: File | string;
      contentType: string;
      supplier?: string;
    }) =>
      apiRequest<{ imported_count: number }>(
        `/api/emails/import?${new URLSearchParams(supplier ? { filename, supplier } : { filename })}`,
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
  const bulkDelete = useMutation({
    mutationFn: (body: { ids?: string[]; import_batch_id?: string }) =>
      apiRequest<{ deleted_count: number }>("/api/emails/bulk-delete", {
        method: "POST",
        body,
      }),
    onSuccess: async (result) => {
      setSelectedIds(new Set());
      setBatchFilter("all");
      setImportMessage(`${result.deleted_count} conta(s) excluída(s).`);
      await refresh();
    },
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
  const batches = useMemo(() => {
    const map = new Map<string, { count: number; firstAt: string }>();
    for (const account of accounts) {
      if (!account.import_batch_id) continue;
      const current = map.get(account.import_batch_id);
      map.set(account.import_batch_id, {
        count: (current?.count ?? 0) + 1,
        firstAt:
          current && current.firstAt < account.created_at
            ? current.firstAt
            : account.created_at,
      });
    }
    return [...map.entries()]
      .sort((a, b) => a[1].firstAt.localeCompare(b[1].firstAt))
      .map(([id, info], index) => ({
        id,
        count: info.count,
        label: `Lote ${index + 1} · ${new Date(info.firstAt).toLocaleString("pt-BR")} · ${info.count} conta(s)`,
      }));
  }, [accounts]);
  const filteredAccounts = accounts.filter(
    (account) =>
      (statusFilter === "all" || account.status === statusFilter) &&
      (batchFilter === "all" || account.import_batch_id === batchFilter) &&
      (responsibleFilter === "all" ||
        (responsibleFilter === "__unassigned__"
          ? account.responsible === null
          : account.responsible === responsibleFilter)),
  );

  const selectedVisible = filteredAccounts.filter((account) => selectedIds.has(account.id));
  const allVisibleSelected =
    filteredAccounts.length > 0 && selectedVisible.length === filteredAccounts.length;

  function toggleSelected(id: string) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  }

  function toggleAllVisible() {
    setSelectedIds((current) => {
      const next = new Set(current);
      for (const account of filteredAccounts) {
        if (allVisibleSelected) next.delete(account.id);
        else next.add(account.id);
      }
      return next;
    });
  }

  function hasLinesWithoutSupplier(text: string) {
    return text.split(/\r?\n/).some((line) => {
      if (!line.trim()) return false;
      const parts = line.includes("\t") ? line.split("\t") : line.split(":");
      return parts.length === 2;
    });
  }

  async function startImport(supplier?: string) {
    if (importMode === "file" && importFile) {
      if (
        supplier === undefined &&
        /\.txt$/i.test(importFile.name) &&
        hasLinesWithoutSupplier(await importFile.text())
      ) {
        setSupplierPromptOpen(true);
        return;
      }
      importAccounts.mutate({
        filename: importFile.name,
        content: importFile,
        contentType: importFile.type || "text/plain",
        supplier,
      });
    } else if (importMode === "text" && importText.trim()) {
      if (supplier === undefined && hasLinesWithoutSupplier(importText)) {
        setSupplierPromptOpen(true);
        return;
      }
      importAccounts.mutate({
        filename: "contas.txt",
        content: importText,
        contentType: "text/plain; charset=utf-8",
        supplier,
      });
    }
  }

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
    errorMessage(bulkDelete.error, "Não foi possível excluir as contas."),
    errorMessage(changeStatus.error, "Não foi possível atualizar o status."),
    errorMessage(saveObservation.error, "Não foi possível salvar a observação."),
    errorMessage(uploadAttachment.error, "Não foi possível enviar o anexo."),
  ].filter(Boolean);
  const importError = errorMessage(importAccounts.error, "Não foi possível importar a planilha.");

  return (
    <div className="mx-auto max-w-[1600px] space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-accent">
            Workspace
          </p>
          <h1 className="mt-2 flex items-center gap-2 text-2xl font-semibold text-fg sm:text-3xl">
            <Mail className="text-accent" size={25} />
            Controle de E-mails
          </h1>
          <p className="mt-2 text-sm text-muted">
            Contas, responsáveis, status e registros de erro do workspace.
          </p>
        </div>
        <a
          className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-line bg-brand-soft px-4 text-sm font-semibold text-accent hover:bg-brand-soft"
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
      {importError && (
        <div
          className="rounded-xl border border-danger/30 bg-danger-soft p-4 text-sm text-danger"
          role="alert"
        >
          {importError.split(/([^\s,;:()]+@[^\s,;:()]+?)(?=[\s,;:()]|\.(?:\s|$)|$)/g).map((part, index) =>
            index % 2 === 1 ? (
              <mark
                className="rounded bg-warning px-1 font-semibold text-white"
                key={index}
              >
                {part}
              </mark>
            ) : (
              part
            ),
          )}
        </div>
      )}

      {emails.data.can_manage && (
        <details className="dashboard-card rounded-xl p-4">
          <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-semibold text-fg">
            <Plus className="text-accent" size={16} />
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
              className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-brand px-4 text-sm font-semibold text-white disabled:opacity-50 sm:col-span-2 xl:col-span-4"
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
        <details className="dashboard-card rounded-xl p-4">
          <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-semibold text-fg">
            <Plus className="text-accent" size={16} />
            Importar contas por arquivo ou texto
          </summary>
          <div className="mt-4 space-y-3">
            <div aria-label="Forma de importar" className="flex flex-wrap gap-2">
              <button
                aria-pressed={importMode === "file"}
                className={`min-h-9 rounded-lg border px-3 text-sm font-medium ${
                  importMode === "file"
                    ? "border-brand bg-brand-soft text-accent"
                    : "border-line text-muted"
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
                    ? "border-brand bg-brand-soft text-accent"
                    : "border-line text-muted"
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
                  <span className="text-xs text-muted">{importFile.name}</span>
                )}
              </div>
            ) : (
              <textarea
                aria-label="Texto das contas"
                className="collaborator-input min-h-36 w-full cursor-pointer resize-y font-mono text-xs"
                onClick={() => setTextModalOpen(true)}
                onFocus={() => setTextModalOpen(true)}
                placeholder={"Fornecedor : email@exemplo.com : senha : codigo 2FA : senha 2FA\nFornecedor : email2@exemplo.com : senha : codigo 2FA : "}
                readOnly
                value={importText}
              />
            )}
            {textModalOpen && createPortal(
              <div
                aria-label="Digitar contas"
                aria-modal="true"
                className="fixed inset-0 z-[100] flex min-h-dvh items-center justify-center overflow-y-auto bg-black/70 p-4"
                role="dialog"
              >
                <div className="flex h-[85dvh] max-h-[calc(100dvh-2rem)] min-h-0 w-full max-w-5xl flex-col gap-3 rounded-xl border border-line bg-well p-4">
                  <h2 className="text-sm font-semibold text-fg">
                    Digite ou cole as contas
                  </h2>
                  <textarea
                    aria-label="Texto das contas (ampliado)"
                    autoFocus
                    className="collaborator-input w-full flex-1 resize-none font-mono text-sm"
                    onChange={(event) => {
                      setImportText(event.target.value);
                      setImportMessage(null);
                    }}
                    placeholder={"Fornecedor : email@exemplo.com : senha : codigo 2FA : senha 2FA"}
                    value={importText}
                  />
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-xs text-muted">
                      {importText.split("\n").filter((line) => line.trim()).length} linha(s)
                    </span>
                    <button
                      className="inline-flex min-h-10 items-center rounded-lg bg-brand px-4 text-sm font-semibold text-white"
                      onClick={() => setTextModalOpen(false)}
                      type="button"
                    >
                      Concluir
                    </button>
                  </div>
                </div>
              </div>,
              document.body,
            )}
            <p className="text-xs text-muted">
              Uma conta por linha: fornecedor : e-mail : senha. Os demais campos (código 2FA e senha 2FA) são
              preenchidos com "-" se omitidos. Se enviar só e-mail : senha, perguntaremos o fornecedor e
              aplicaremos a todas essas linhas. Também aceitamos tabulação.
            </p>
            <button
              className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-brand px-4 text-sm font-semibold text-white disabled:opacity-50"
              disabled={
                importAccounts.isPending ||
                (importMode === "file" ? !importFile : !importText.trim())
              }
              onClick={() => void startImport()}
              type="button"
            >
              {importAccounts.isPending ? "Importando..." : "Importar"}
            </button>
            {supplierPromptOpen && createPortal(
              <div
                aria-label="Informar fornecedor"
                aria-modal="true"
                className="fixed inset-0 z-[100] flex min-h-dvh items-center justify-center overflow-y-auto bg-black/70 p-4"
                role="dialog"
              >
                <form
                  className="grid w-full max-w-md gap-3 rounded-xl border border-line bg-well p-4"
                  onSubmit={(event: FormEvent) => {
                    event.preventDefault();
                    const supplier = bulkSupplier.trim();
                    if (!supplier) return;
                    setSupplierPromptOpen(false);
                    void startImport(supplier);
                  }}
                >
                  <h2 className="text-sm font-semibold text-fg">Qual o fornecedor?</h2>
                  <p className="text-xs text-muted">
                    Algumas linhas têm só e-mail e senha. O fornecedor informado será aplicado a elas.
                  </p>
                  <input
                    autoFocus
                    className="collaborator-input"
                    maxLength={120}
                    onChange={(event) => setBulkSupplier(event.target.value)}
                    placeholder="Fornecedor"
                    value={bulkSupplier}
                  />
                  <div className="flex justify-end gap-2">
                    <button
                      className="min-h-10 rounded-lg border border-line px-4 text-sm text-muted"
                      onClick={() => setSupplierPromptOpen(false)}
                      type="button"
                    >
                      Cancelar
                    </button>
                    <button
                      className="min-h-10 rounded-lg bg-brand px-4 text-sm font-semibold text-white disabled:opacity-50"
                      disabled={!bulkSupplier.trim()}
                      type="submit"
                    >
                      Importar
                    </button>
                  </div>
                </form>
              </div>,
              document.body,
            )}
            {importMessage && <p className="text-sm text-success">{importMessage}</p>}
          </div>
        </details>
      )}

      <section className="dashboard-card space-y-4 rounded-xl p-4 sm:p-4">
        <div className="flex flex-wrap items-center gap-3">
          <label className="grid gap-1 text-xs text-muted">
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
          <label className="grid gap-1 text-xs text-muted">
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
          <span className="ml-auto text-xs text-muted">
            {filteredAccounts.length} de {accounts.length} conta(s)
          </span>
        </div>

        {emails.data.can_manage && (
          <div className="flex flex-wrap items-end gap-3">
            <label className="grid gap-1 text-xs text-muted">
              Lote importado
              <select
                className="collaborator-input min-w-64"
                onChange={(event) => setBatchFilter(event.target.value)}
                value={batchFilter}
              >
                <option value="all">Todos os lotes</option>
                {batches.map((batch) => (
                  <option key={batch.id} value={batch.id}>{batch.label}</option>
                ))}
              </select>
            </label>
            <button
              className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-danger/30 px-3 text-sm text-danger hover:bg-danger-soft disabled:opacity-40"
              disabled={batchFilter === "all" || bulkDelete.isPending}
              onClick={async () => {
                const batch = batches.find((item) => item.id === batchFilter);
                if (batch && await confirmAction(`Excluir todas as ${batch.count} contas deste lote?`)) {
                  bulkDelete.mutate({ import_batch_id: batch.id });
                }
              }}
              type="button"
            >
              <Trash2 size={14} /> Excluir lote
            </button>
            <button
              className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-danger/30 px-3 text-sm text-danger hover:bg-danger-soft disabled:opacity-40"
              disabled={selectedVisible.length === 0 || bulkDelete.isPending}
              onClick={async () => {
                if (await confirmAction(`Excluir ${selectedVisible.length} conta(s) selecionada(s)?`)) {
                  bulkDelete.mutate({ ids: selectedVisible.map((account) => account.id) });
                }
              }}
              type="button"
            >
              <Trash2 size={14} /> Excluir selecionados ({selectedVisible.length})
            </button>
          </div>
        )}

        {filteredAccounts.length === 0 ? (
          <EmptyState message="Nenhuma conta corresponde aos filtros." />
        ) : (
          <div className="overflow-x-auto rounded-lg border border-line-soft">
            <table className="w-full min-w-[1500px] border-collapse text-left text-xs">
              <thead className="bg-well text-[10px] uppercase tracking-[0.1em] text-muted">
                <tr>
                  {emails.data.can_manage && (
                    <th className="px-3 py-3">
                      <input
                        aria-label="Selecionar todas"
                        checked={allVisibleSelected}
                        onChange={toggleAllVisible}
                        type="checkbox"
                      />
                    </th>
                  )}
                  <th className="px-3 py-3">#</th>
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
              <tbody className="divide-y divide-line-soft">
                {filteredAccounts.map((account, accountIndex) => (
                  <tr className="align-top hover:bg-surface-raised" key={account.id}>
                    {emails.data.can_manage && (
                      <td className="px-3 py-3">
                        <input
                          aria-label={`Selecionar ${account.email}`}
                          checked={selectedIds.has(account.id)}
                          onChange={() => toggleSelected(account.id)}
                          type="checkbox"
                        />
                      </td>
                    )}
                    <td className="px-3 py-3 text-muted">{accountIndex + 1}</td>
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
                        <td className="px-3 py-3 text-muted">{account.responsible ?? "—"}</td>
                        <td className="px-3 py-3"><span className={`rounded-full border px-2 py-1 ${statusStyles[account.status]}`}><StatusLabel status={account.status} /></span></td>
                        <td className="px-3 py-3 text-muted">{account.observation || "—"}</td>
                        <td className="px-2 py-2">
                          <input aria-label="Código 2FA" className="collaborator-input min-w-36" value={editForm.two_factor_code} onChange={(event) => setEditForm({ ...editForm, two_factor_code: event.target.value })} />
                        </td>
                        <td className="px-2 py-2">
                          <input aria-label="Senha do 2FA" className="collaborator-input min-w-36" value={editForm.two_factor_password} onChange={(event) => setEditForm({ ...editForm, two_factor_password: event.target.value })} />
                        </td>
                        <td className="px-3 py-3">{account.attachment_url ? <a className="text-accent" href={account.attachment_url} rel="noreferrer" target="_blank">Ver imagem</a> : "—"}</td>
                        <td className="px-2 py-2">
                          <div className="flex gap-2">
                            <button aria-label="Salvar edição" className="rounded border border-success/30 p-2 text-success" disabled={updateAccount.isPending} onClick={() => updateAccount.mutate({ id: account.id, form: editForm })} type="button"><Save size={14} /></button>
                            <button aria-label="Cancelar edição" className="rounded border border-line p-2 text-muted" onClick={() => setEditingId(null)} type="button">×</button>
                          </div>
                        </td>
                      </>
                    ) : (
                      <>
                        <td className="px-3 py-3 font-medium text-fg-2">{account.supplier}</td>
                        <td className="px-3 py-3"><CopyValue label="E-mail" value={account.email} /></td>
                        <td className="px-3 py-3"><CopyValue label="Senha" value={account.password} /></td>
                        <td className="px-3 py-3 text-fg-2">{account.responsible ?? "—"}</td>
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
                              className="mt-1 inline-flex items-center gap-1 rounded border border-line px-2 py-1 text-[10px] text-accent"
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
                                <img alt="Anexo de erro" className="size-10 rounded border border-line object-cover" src={account.attachment_url} />
                              </a>
                            )}
                            <label className="inline-flex cursor-pointer items-center gap-1 rounded border border-line px-2 py-2 text-accent hover:bg-brand-soft">
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
                                className="rounded border border-line p-2 text-accent hover:bg-brand-soft"
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
                                className="rounded border border-danger/30 p-2 text-danger hover:bg-danger-soft"
                                onClick={async () => {
                                  if (await confirmAction(`Excluir a conta ${account.email}?`)) deleteAccount.mutate(account.id);
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
