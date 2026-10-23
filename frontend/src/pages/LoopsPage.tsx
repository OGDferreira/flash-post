import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ChevronDown,
  Clock3,
  Copy,
  Folder,
  Image as ImageIcon,
  Infinity,
  Pause,
  Pencil,
  Play,
  Plus,
  Trash2,
  Video,
  X,
} from "lucide-react";

import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { Modal } from "@/components/ui/Modal";
import { apiRequest } from "@/services/api";
import { LoopHealthPanel } from "@/components/LoopHealthPanel";
import {
  formatAccountConnectedAt,
  formatConnectedDuration,
} from "@/features/instagram/accountDates";
import { confirmAction } from "@/lib/confirm";
import { ShareLoopButton, SharedLoopsSection } from "@/features/partners/SharedTemplates";
import { type InstagramMedia, type InstagramMediaResponse, type InstagramFoldersResponse, type InstagramLoop, type InstagramLoopAccountsPage, type InstagramLoopsResponse, type PublicationFailuresResponse, groupFailuresByAccount, type LoopForm, emptyForm, MAX_UPLOAD_BYTES, formatDate, apiErrorMessage, mediaFitsLoop, fileFitsLoop } from "@/pages/loops/loopShared";

function LoopAccountsList({ loopId }: { loopId: string }) {
  const [offset, setOffset] = useState(0);
  const [loadedAccounts, setLoadedAccounts] = useState<InstagramLoopAccountsPage["accounts"]>([]);
  const accounts = useQuery({
    queryKey: ["loops", "accounts", "details", loopId, offset],
    queryFn: () => {
      const params = new URLSearchParams({
        loop_id: loopId,
        only_loop_accounts: "true",
        limit: "50",
        offset: String(offset),
      });
      return apiRequest<InstagramLoopAccountsPage>(`/api/loops/accounts?${params}`);
    },
    placeholderData: (previous) => previous,
    retry: false,
  });
  useEffect(() => {
    if (!accounts.data) return;
    setLoadedAccounts((current) => {
      const next = offset === 0 ? [] : current;
      const knownIds = new Set(next.map((account) => account.id));
      return [...next, ...accounts.data.accounts.filter((account) => !knownIds.has(account.id))];
    });
  }, [accounts.data, offset]);
  if (accounts.isLoading && loadedAccounts.length === 0) return <LoadingState label="Carregando contas do loop" />;
  if (accounts.error || !accounts.data) {
    return <ErrorState message="Não foi possível carregar as contas deste loop." />;
  }
  return (
    <div className="mt-3 flex flex-wrap gap-1.5">
      {loadedAccounts.map((account) => (
        <div className="rounded bg-well px-2 py-1 text-xs text-fg-2" key={account.id}>
          <p>@{account.username}</p>
          <p className="mt-0.5 text-[10px] text-muted">
            Conectada em {formatAccountConnectedAt(account.connected_at)}
          </p>
          {account.status === "error" && (
            <p className="mt-0.5 text-[10px] text-danger">
              Duração antes do erro: {formatConnectedDuration(account.connected_at, account.error_at)}
            </p>
          )}
        </div>
      ))}
      {loadedAccounts.length === 0 && (
        <p className="text-xs text-muted">Nenhuma conta conectada neste loop.</p>
      )}
      {loadedAccounts.length < accounts.data.total && (
        <button
          className="min-h-8 rounded-lg border border-line px-3 text-xs text-fg-2 hover:text-white disabled:opacity-50"
          disabled={accounts.isFetching}
          onClick={() => setOffset(loadedAccounts.length)}
          type="button"
        >
          {accounts.isFetching ? "Carregando..." : `Carregar mais (${accounts.data.total - loadedAccounts.length} restantes)`}
        </button>
      )}
    </div>
  );
}

export function LoopsPage() {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<"continuous" | "errors">("continuous");
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [initializedAccountsKey, setInitializedAccountsKey] = useState<string | null>(null);
  const [expandedLoops, setExpandedLoops] = useState<string[]>([]);
  const toggleLoop = (id: string) =>
    setExpandedLoops((current) => (current.includes(id) ? current.filter((item) => item !== id) : [...current, id]));
  const [form, setForm] = useState<LoopForm>(emptyForm);
  const [uploadCaption, setUploadCaption] = useState("");
  const [uploadValidationError, setUploadValidationError] = useState<string | null>(null);
  const [uploadingBatch, setUploadingBatch] = useState(false);
  const [poolSelected, setPoolSelected] = useState<Set<string>>(new Set());
  const loops = useQuery({
    queryKey: ["loops"],
    queryFn: () => apiRequest<InstagramLoopsResponse>("/api/loops?include_accounts=false"),
    refetchInterval: 120_000,
    retry: false,
  });
  const media = useQuery({
    queryKey: ["instagram-media"],
    queryFn: () => apiRequest<InstagramMediaResponse>("/api/media"),
    retry: false,
  });
  const folders = useQuery({
    queryKey: ["instagram", "folders"],
    queryFn: () => apiRequest<InstagramFoldersResponse>("/api/instagram/folders?include_accounts=false"),
    retry: false,
  });
  const editAccounts = useQuery({
    queryKey: ["loops", "accounts", editingId],
    queryFn: () => {
      const params = new URLSearchParams({ limit: "1000" });
      if (editingId) params.set("loop_id", editingId);
      return apiRequest<InstagramLoopAccountsPage>(`/api/loops/accounts?${params}`);
    },
    enabled: formOpen,
    staleTime: 30_000,
    retry: false,
  });
  useEffect(() => {
    const key = editingId ?? "new-loop";
    if (!formOpen || !editAccounts.data || initializedAccountsKey === key) return;
    setForm((current) => ({
      ...current,
      account_ids: editAccounts.data.selected_ids,
    }));
    setInitializedAccountsKey(key);
  }, [editAccounts.data, editingId, formOpen, initializedAccountsKey]);
  const failures = useQuery({
    queryKey: ["loops", "failures"],
    queryFn: () => apiRequest<PublicationFailuresResponse>("/api/loops/failures"),
    enabled: loops.data?.can_configure === true,
    refetchInterval: 120_000,
    retry: false,
  });
  const failureGroups = useMemo(
    () => groupFailuresByAccount(failures.data?.failures ?? []),
    [failures.data?.failures],
  );
  const [openFailureAccounts, setOpenFailureAccounts] = useState<Set<string>>(new Set());
  const retryJobs = useMutation({
    mutationFn: (jobIds: string[]) =>
      apiRequest<{ requeued: number }>("/api/loops/failures/retry", {
        method: "POST",
        body: { job_ids: jobIds },
      }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["loops"] }),
  });

  const saveLoop = useMutation({
    mutationFn: () => {
      if (!editingId) {
        return apiRequest<InstagramLoop>("/api/loops", {
          method: "POST",
          body: form,
        });
      }
      if (loops.data?.can_configure) {
        return apiRequest<InstagramLoop>(`/api/loops/${editingId}`, {
          method: "PUT",
          body: form,
        });
      }
      return apiRequest<InstagramLoop>(`/api/loops/${editingId}/accounts`, {
        method: "PUT",
        body: { account_ids: form.account_ids },
      });
    },
    onSuccess: () => {
      setForm(emptyForm);
      setFormOpen(false);
      setEditingId(null);
      void queryClient.invalidateQueries({ queryKey: ["loops"] });
      void queryClient.invalidateQueries({ queryKey: ["instagram-media"] });
    },
  });
  const changeStatus = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      apiRequest(`/api/loops/${id}/status`, {
        method: "PATCH",
        body: { enabled },
      }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["loops"] }),
  });
  const cloneLoop = useMutation({
    mutationFn: (id: string) =>
      apiRequest<InstagramLoop>(`/api/loops/${id}/clone`, { method: "POST" }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["loops"] }),
  });
  const deleteLoop = useMutation({
    mutationFn: (id: string) => apiRequest(`/api/loops/${id}`, { method: "DELETE" }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["loops"] }),
  });
  const removeLoopMedia = useMutation({
    mutationFn: ({ loopId, mediaId }: { loopId: string; mediaId: string }) =>
      apiRequest(`/api/loops/${loopId}/media/${mediaId}`, { method: "DELETE" }),
    onSuccess: (_result, { mediaId }) => {
      setForm((current) => ({
        ...current,
        media_ids: current.media_ids.filter((id) => id !== mediaId),
      }));
      void queryClient.invalidateQueries({ queryKey: ["loops"] });
    },
  });
  const uploadMedia = useMutation({
    mutationFn: ({ file, caption }: { file: File; caption: string }) => {
      const query = new URLSearchParams({ filename: file.name });
      if (caption) query.set("caption", caption);
      return apiRequest<InstagramMedia>(`/api/media?${query}`, {
        method: "POST",
        headers: { "Content-Type": file.type },
        body: file,
      });
    },
    onSuccess: (uploaded) => {
      setForm((current) => ({
        ...current,
        media_ids: mediaFitsLoop(uploaded, current.post_type)
          ? [...new Set([...current.media_ids, uploaded.id])]
          : current.media_ids,
      }));
      void queryClient.invalidateQueries({ queryKey: ["instagram-media"] });
    },
  });
  const [coverError, setCoverError] = useState<string | null>(null);
  const uploadCover = useMutation({
    // target: null = the cover of every video, else the id of one video
    mutationFn: ({ file }: { file: File; target: string | null }) =>
      apiRequest<InstagramMedia>(
        `/api/media?${new URLSearchParams({ filename: file.name, purpose: "cover" })}`,
        { method: "POST", headers: { "Content-Type": file.type }, body: file },
      ),
    onSuccess: (uploaded, { target }) => {
      setForm((current) =>
        target === null
          ? { ...current, cover_media_id: uploaded.id }
          : { ...current, media_covers: { ...current.media_covers, [target]: uploaded.id } },
      );
      void queryClient.invalidateQueries({ queryKey: ["instagram-media"] });
    },
  });
  function pickCover(files: FileList | null, target: string | null) {
    const file = files?.[0];
    setCoverError(null);
    if (!file) return;
    if (file.type !== "image/jpeg" || file.size > MAX_UPLOAD_BYTES) {
      setCoverError("A capa precisa ser uma imagem JPEG de até 50 MB.");
      return;
    }
    uploadCover.mutate({ file, target });
  }
  const showsCover = form.post_type !== "images";
  const visibleLoops = useMemo(
    () =>
      // A partner's linked copies live in the "Loops compartilhados" area, not in this list.
      (loops.data?.loops ?? []).filter(
        (loop) => tab !== "errors" && !loop.linked,
      ),
    [loops.data?.loops, tab],
  );

  if (loops.isLoading) return <LoadingState label="Carregando loops" />;
  if (loops.error || !loops.data) {
    return <ErrorState message="Não foi possível carregar os loops deste workspace." />;
  }

  const mutationError = [
    apiErrorMessage(saveLoop.error, "Não foi possível salvar o loop."),
    apiErrorMessage(changeStatus.error, "Não foi possível alterar o estado do loop."),
    apiErrorMessage(cloneLoop.error, "Não foi possível clonar o loop."),
    apiErrorMessage(deleteLoop.error, "Não foi possível remover o loop."),
    apiErrorMessage(removeLoopMedia.error, "Não foi possível remover a mídia deste loop."),
    apiErrorMessage(uploadMedia.error, "Não foi possível enviar a mídia."),
    apiErrorMessage(uploadCover.error, "Não foi possível enviar a capa."),
  ].find(Boolean);

  async function uploadFiles(files: File[]) {
    setUploadValidationError(null);
    const invalidFile = files.find(
      (file) =>
        file.size > MAX_UPLOAD_BYTES ||
        !fileFitsLoop(file, form.post_type),
    );
    if (invalidFile) {
      setUploadValidationError(
        "Selecione arquivos compatíveis com o tipo do loop: JPEG para imagens ou MP4 para Reels, até 50 MB cada.",
      );
      return;
    }

    setUploadingBatch(true);
    try {
      const caption = uploadCaption.trim();
      for (const file of files) {
        await uploadMedia.mutateAsync({ file, caption });
      }
      setUploadCaption("");
    } catch {
      setUploadValidationError(
        "O envio em lote foi interrompido. Os arquivos enviados antes da falha permanecem salvos no pool.",
      );
    } finally {
      setUploadingBatch(false);
    }
  }

  function beginEdit(loop: InstagramLoop) {
    setEditingId(loop.id);
    setInitializedAccountsKey(null);
    setForm({
      name: loop.name,
      interval_min_minutes: loop.interval_min_minutes,
      interval_max_minutes: loop.interval_max_minutes,
      daily_limit_per_account: loop.daily_limit_per_account ?? 100,
      post_type: loop.post_type,
      repeat_media: loop.repeat_media,
      media_ids: loop.media_ids,
      auto_folder_ids: loop.auto_folder_ids ?? [],
      media_captions: {},
      caption_mode: loop.caption_mode ?? "per_media",
      caption: loop.caption ?? "",
      cover_mode: loop.cover_mode ?? "auto",
      cover_media_id: loop.cover_media_id ?? null,
      media_covers: {},
      account_ids: loop.accounts.map((account) => account.id),
    });
    setFormOpen(true);
    saveLoop.reset();
  }

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="mt-2 flex items-center gap-2 text-2xl font-semibold tracking-[-0.045em] text-fg sm:text-3xl">
            <Infinity size={27} className="text-accent" />
            Loops
          </h2>
        </div>
        {loops.data.can_configure && (
          <button
            className="inline-flex min-h-10 items-center gap-2 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-strong"
            type="button"
            onClick={() => {
              setEditingId(null);
              setInitializedAccountsKey(null);
              setForm(emptyForm);
              setFormOpen((open) => !open);
              saveLoop.reset();
            }}
          >
            {formOpen ? <X size={16} /> : <Plus size={16} />}
            {formOpen ? "Fechar" : "Novo loop"}
          </button>
        )}
      </header>
      {loops.data.can_configure && (
        <SharedLoopsSection loops={loops.data.loops} />
      )}

      {!loops.data.publishing_enabled ? (
        <div className="rounded-lg border border-warning/30 bg-warning-soft p-4 text-sm text-warning">
          <p className="flex items-start gap-2">
            <AlertTriangle size={17} className="mt-0.5 shrink-0" />
            <span className="min-w-0">
              As publicações automáticas estão desativadas no servidor. Configure
              {" "}<code className="break-all font-mono">INSTAGRAM_PUBLISHING_ENABLED=true</code>
              {" "}no serviço Web do Render e reinicie ou reimplante o serviço para habilitá-las.
            </span>
          </p>
        </div>
      ) : (
        <div className="rounded-lg border border-success/30 bg-success-soft p-4 text-sm text-success">
          Publicações automáticas habilitadas. O worker precisa estar ativo para processar a fila.
        </div>
      )}
      {mutationError && <ErrorState message={mutationError} />}
      {!loops.data.can_manage && (
        <p className="rounded-lg border border-line bg-surface-raised px-4 py-3 text-sm text-fg-2">
          Você pode consultar os loops. Somente o OWNER pode configurá-los.
        </p>
      )}

      <div className="flex gap-1 border-b border-line">
        {([
          ["continuous", "Loops"],
        ] as const).map(([value, label]) => (
          <button
            className={`border-b-2 px-4 py-3 text-sm ${
              tab === value
                ? "border-brand font-medium text-white"
                : "border-transparent text-muted hover:text-white"
            }`}
            key={value}
            type="button"
            onClick={() => setTab(value)}
          >
            {label}
          </button>
        ))}
        {loops.data.can_configure && (
        <button
          className={`border-b-2 px-4 py-3 text-sm ${
            tab === "errors"
              ? "border-brand font-medium text-white"
              : "border-transparent text-muted hover:text-white"
          }`}
          type="button"
          onClick={() => setTab("errors")}
        >
          Falhas de Publicação ({failures.data ? failureGroups.length : loops.data.loops.reduce((total, loop) => total + loop.failed_count, 0)})
        </button>
        )}
      </div>
      {tab === "errors" ? (
        failures.isLoading ? (
        <LoadingState label="Carregando log de erros" />
        ) : failures.error || !failures.data ? (
        <ErrorState message="Não foi possível carregar o log de erros." />
        ) : failures.data.failures.length === 0 ? (
        <EmptyState message="Nenhuma falha de publicação registrada." />
        ) : (
        <section aria-label="Falhas de publicação" className="space-y-3">
          {failureGroups.map((group) => {
            const open = openFailureAccounts.has(group.accountId);
            return (
              <article
                className="rounded-xl border border-danger/30 bg-danger-soft"
                key={group.accountId}
              >
                <button
                  aria-expanded={open}
                  className="flex w-full flex-wrap items-center justify-between gap-2 p-4 text-left"
                  type="button"
                  onClick={() =>
                    setOpenFailureAccounts((current) => {
                      const next = new Set(current);
                      if (!next.delete(group.accountId)) next.add(group.accountId);
                      return next;
                    })
                  }
                >
                  <span>
                    <span className="flex flex-wrap items-center gap-2 font-medium text-fg">
                      @{group.username}
                      <span
                        className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${
                          group.inLoop
                            ? "bg-success-soft text-success"
                            : "bg-[#2b2a1a] text-warning"
                        }`}
                      >
                        {group.inLoop ? "Ativa" : "Desativada"}
                      </span>
                      {group.accountStatus && group.accountStatus !== "connected" && (
                        <span className="rounded-full bg-danger-soft px-2 py-0.5 text-[10px] font-semibold uppercase text-danger">
                          {group.accountStatus === "error" ? "Conta com erro" : "Conta desconectada"}
                        </span>
                      )}
                    </span>
                    <span className="block text-xs text-muted">
                      {group.loopNames.join(", ")}
                    </span>
                  </span>
                  <span className="flex items-center gap-3 text-xs">
                    <span className="rounded-full bg-danger-soft px-2 py-1 text-danger">
                      {group.failures.length}{" "}
                      {group.failures.length === 1 ? "falha" : "falhas"}
                    </span>
                    <span className="text-muted">{open ? "Ocultar" : "Ver detalhes"}</span>
                  </span>
                </button>
                {open && (
                  <div className="space-y-2 border-t border-danger/30 p-4">
                    <p
                      className={`text-xs ${group.inLoop ? "text-success" : "text-warning"}`}
                    >
                      {group.inLoop
                        ? "A conta continua no loop e tentará o próximo vídeo na próxima rodada."
                        : "A conta não está mais em um loop."}
                    </p>
                    {loops.data.can_manage && (
                      <button
                        className="rounded-lg border border-brand px-3 py-1.5 text-xs text-white hover:bg-well disabled:opacity-60"
                        disabled={retryJobs.isPending}
                        onClick={() => retryJobs.mutate(group.failures.map((item) => item.id))}
                        type="button"
                      >
                        Tentar novamente ({group.failures.length})
                      </button>
                    )}
                    {group.failures.map((failure) => (
                      <div
                        className="space-y-1 rounded-lg border border-line bg-danger-soft p-3"
                        key={failure.id}
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="break-all text-sm text-fg">
                            {failure.media_filename ?? "Mídia não identificada"}
                          </span>
                          <time className="text-xs text-muted">
                            {formatDate(failure.updated_at)}
                          </time>
                        </div>
                        <p className="text-xs text-muted">
                          {failure.loop_name} · {failure.attempts}{" "}
                          {failure.attempts === 1 ? "tentativa" : "tentativas"}
                          {failure.error_category ? ` · ${failure.error_category}` : ""}
                        </p>
                        <p className="break-words text-sm leading-6 text-danger">
                          {failure.error}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </article>
            );
          })}
        </section>
        )
      ) : (
        <div className="space-y-4">
      <p className="text-sm leading-6 text-muted">
        Cada loop escolhe a próxima execução aleatoriamente dentro do intervalo configurado e
        usa uma lista de mídias independente. A primeira publicação entra na fila assim que o loop
        é criado com contas e mídias; o intervalo controla as publicações seguintes.
      </p>

      <Modal
        busy={saveLoop.isPending}
        onClose={() => {
          setFormOpen(false);
          setEditingId(null);
          setInitializedAccountsKey(null);
          setForm(emptyForm);
        }}
        open={formOpen && loops.data.can_manage}
        title={!loops.data.can_configure && editingId
          ? "Associar contas ao loop"
          : editingId
            ? "Editar loop"
            : "Novo loop"}
        wide
      >
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            saveLoop.mutate();
          }}
        >
          <fieldset className="space-y-3 rounded-lg border border-line bg-surface-inset p-3">
            <legend className="px-1 text-sm font-medium text-fg-2">
              Contas Instagram ({form.account_ids.length} selecionadas)
            </legend>
            {editAccounts.isLoading ? (
              <LoadingState label="Carregando contas conectadas" />
            ) : editAccounts.error ? (
              <ErrorState message="Não foi possível carregar as contas conectadas." />
            ) : editAccounts.data?.total === 0 ? (
              <p className="text-sm text-warning">
                Não há contas ativas com token válido. Conecte ou reconecte uma conta no Hub de
                Contas antes de criar o loop.
              </p>
            ) : (
              <div className="space-y-3">
                {[
                  ...(folders.data?.folders ?? []).map((folder) => ({
                    id: folder.id,
                    label: folder.name,
                    color: folder.color,
                    accounts: (editAccounts.data?.accounts ?? []).filter(
                      (account) => account.profile_folder_id === folder.id,
                    ),
                  })),
                  {
                    id: "unassigned",
                    label: "Sem pasta",
                    color: "#64748b",
                    accounts: (editAccounts.data?.accounts ?? []).filter(
                      (account) => !account.profile_folder_id,
                    ),
                  },
                ]
                  .filter((folder) => folder.accounts.length > 0 || folder.id !== "unassigned")
                  .map((folder) => (
                    <section key={folder.id}>
                      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                        <h4 className="flex items-center gap-2 text-xs text-muted">
                          <Folder size={13} style={{ color: folder.color }} />
                          {folder.label} ({folder.accounts.length})
                        </h4>
                        {folder.id !== "unassigned" && (
                          <label
                            className="flex cursor-pointer items-center gap-1.5 text-[11px] text-fg-2"
                            title="Toda conta que entrar nesta pasta passa a fazer parte deste loop automaticamente"
                          >
                            <input
                              checked={form.auto_folder_ids.includes(folder.id)}
                              className="accent-[#00c9d8]"
                              disabled={!loops.data.can_manage}
                              onChange={() =>
                                setForm((current) => ({
                                  ...current,
                                  auto_folder_ids: current.auto_folder_ids.includes(folder.id)
                                    ? current.auto_folder_ids.filter((id) => id !== folder.id)
                                    : [...current.auto_folder_ids, folder.id],
                                }))
                              }
                              type="checkbox"
                            />
                            Entrar no loop automaticamente
                          </label>
                        )}
                        <button
                          className="text-[11px] font-medium text-accent hover:text-white disabled:opacity-50"
                          disabled={!loops.data.can_manage}
                          onClick={() => {
                            const folderAccountIds = folder.accounts.map(({ id }) => id);
                            const allSelected = folderAccountIds.every((id) =>
                              form.account_ids.includes(id),
                            );
                            setForm((current) => ({
                              ...current,
                              account_ids: allSelected
                                ? current.account_ids.filter(
                                    (id) => !folderAccountIds.includes(id),
                                  )
                                : [...new Set([...current.account_ids, ...folderAccountIds])],
                            }));
                          }}
                          type="button"
                        >
                          {folder.accounts.every(({ id }) => form.account_ids.includes(id))
                            ? "Desmarcar pasta"
                            : "Selecionar pasta"}
                        </button>
                      </div>
                      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                        {folder.accounts.map((account) => {
                          const checked = form.account_ids.includes(account.id);
                          return (
                            <label
                              className={`flex min-h-10 cursor-pointer items-center gap-2 rounded-lg border px-3 text-xs ${
                                checked
                                  ? "border-brand bg-brand-soft text-fg"
                                  : "border-line text-fg-2"
                              }`}
                              key={account.id}
                              style={checked ? undefined : { borderColor: `${folder.color}66` }}
                            >
                              <input
                                className="accent-[#00c9d8]"
                                type="checkbox"
                                checked={checked}
                                onChange={() =>
                                  setForm((current) => ({
                                    ...current,
                                    account_ids: current.account_ids.includes(account.id)
                                      ? current.account_ids.filter((id) => id !== account.id)
                                      : [...current.account_ids, account.id],
                                  }))
                                }
                              />
                              @{account.username}
                            </label>
                          );
                        })}
                      </div>
                    </section>
                  ))}
              </div>
            )}
          </fieldset>
          {loops.data.can_configure && (
            <section className="space-y-3 rounded-lg border border-line bg-surface-inset p-3">
              <h4 className="text-sm font-medium text-fg-2">Legenda e capa dos posts</h4>
              <fieldset className="space-y-2">
                <legend className="mb-1 text-xs text-muted">Legenda</legend>
                <div className="flex flex-wrap gap-2">
                  {([
                    ["per_media", "Uma legenda por vídeo"],
                    ["all", "Mesma legenda para todos"],
                  ] as const).map(([value, label]) => (
                    <button
                      className={`min-h-9 rounded-lg border px-3 py-1.5 text-xs ${
                        form.caption_mode === value
                          ? "border-brand bg-brand-soft text-accent"
                          : "border-line text-muted hover:bg-surface-raised"
                      }`}
                      key={value}
                      type="button"
                      onClick={() => setForm((current) => ({ ...current, caption_mode: value }))}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                {form.caption_mode === "all" ? (
                  <textarea
                    aria-label="Legenda de todos os posts"
                    className="min-h-20 w-full rounded-lg border border-line bg-surface-inset px-3 py-2 text-sm text-fg outline-none focus:border-brand"
                    maxLength={2200}
                    placeholder="Esta legenda vai em todos os posts do loop"
                    value={form.caption}
                    onChange={(event) => setForm((current) => ({ ...current, caption: event.target.value }))}
                  />
                ) : (
                  <p className="text-xs text-muted">Cada vídeo usa a legenda escrita nele, na lista abaixo.</p>
                )}
              </fieldset>
              {showsCover && (
                <fieldset className="space-y-2">
                  <legend className="mb-1 text-xs text-muted">Capa dos Reels</legend>
                  <div className="flex flex-wrap gap-2">
                    {([
                      ["auto", "Automática"],
                      ["all", "Uma capa para todos"],
                      ["per_media", "Uma capa por vídeo"],
                    ] as const).map(([value, label]) => (
                      <button
                        className={`min-h-9 rounded-lg border px-3 py-1.5 text-xs ${
                          form.cover_mode === value
                            ? "border-brand bg-brand-soft text-accent"
                            : "border-line text-muted hover:bg-surface-raised"
                        }`}
                        key={value}
                        type="button"
                        onClick={() => setForm((current) => ({ ...current, cover_mode: value }))}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  {form.cover_mode === "auto" && (
                    <p className="text-xs text-muted">O Instagram escolhe um quadro do vídeo como capa.</p>
                  )}
                  {form.cover_mode === "all" && (
                    <CoverPicker
                      coverId={form.cover_media_id}
                      disabled={uploadCover.isPending}
                      label="Imagem de capa de todos os vídeos"
                      onPick={(files) => pickCover(files, null)}
                      onClear={() => setForm((current) => ({ ...current, cover_media_id: null }))}
                    />
                  )}
                  {form.cover_mode === "all" && !form.cover_media_id && (
                    <p className="text-xs text-warning">Envie a imagem JPEG da capa para salvar.</p>
                  )}
                  {form.cover_mode === "per_media" && (
                    <p className="text-xs text-muted">
                      Escolha a capa de cada vídeo na lista abaixo. Vídeo sem capa usa a automática.
                    </p>
                  )}
                  {uploadCover.isPending && <p className="text-xs text-accent">Enviando capa...</p>}
                  {coverError && <p className="text-xs text-danger" role="alert">{coverError}</p>}
                </fieldset>
              )}
            </section>
          )}
          <section className="space-y-2 rounded-lg border border-line bg-surface-inset p-3">
            <h4 className="flex flex-wrap items-center justify-between gap-2 text-sm font-medium text-fg-2">
              <span>Mídias do loop ({form.media_ids.length})</span>
              {loops.data.can_configure && form.media_ids.length > 0 && (
                <span className="flex flex-wrap items-center gap-2 text-xs font-normal">
                  <button
                    className="text-accent hover:text-white"
                    type="button"
                    onClick={() =>
                      setPoolSelected(
                        poolSelected.size === form.media_ids.length
                          ? new Set()
                          : new Set(form.media_ids),
                      )
                    }
                  >
                    {poolSelected.size === form.media_ids.length
                      ? "Limpar seleção"
                      : "Selecionar todos"}
                  </button>
                  <button
                    className="rounded border border-danger/30 px-2 py-1 text-danger hover:bg-danger-soft disabled:opacity-40"
                    type="button"
                    disabled={poolSelected.size === 0}
                    onClick={async () => {
                      if (
                        !await confirmAction(
                          `Remover ${poolSelected.size} mídia(s) deste loop?`,
                        )
                      )
                        return;
                      setForm((current) => ({
                        ...current,
                        media_ids: current.media_ids.filter((id) => !poolSelected.has(id)),
                      }));
                      setPoolSelected(new Set());
                    }}
                  >
                    Remover selecionados ({poolSelected.size})
                  </button>
                </span>
              )}
            </h4>
            {form.media_ids.length === 0 ? (
              <p className="text-xs text-muted">
                Nenhuma mídia no loop. Envie arquivos do seu computador na seção de configurações.
              </p>
            ) : (
              <ul className="max-h-72 space-y-1 overflow-y-auto">
                {form.media_ids.map((mediaId) => {
                  const item = media.data?.media.find((entry) => entry.id === mediaId);
                  return (
                    <li
                      className="flex items-center justify-between gap-3 rounded border border-line-soft px-2 py-1.5 text-xs text-fg-2"
                      key={mediaId}
                    >
                      {loops.data.can_configure && (
                        <input
                          className="accent-[#00c9d8]"
                          type="checkbox"
                          aria-label="Selecionar mídia"
                          checked={poolSelected.has(mediaId)}
                          onChange={() => {
                            const next = new Set(poolSelected);
                            if (!next.delete(mediaId)) next.add(mediaId);
                            setPoolSelected(next);
                          }}
                        />
                      )}
                      <span className="flex min-w-0 flex-1 flex-col gap-1">
                        <span className="truncate">{item?.filename ?? "Arquivo indisponível"}</span>
                        {loops.data.can_configure && item && form.caption_mode === "per_media" && (
                          <input
                            aria-label={`Legenda de ${item.filename}`}
                            className="min-h-9 w-full rounded border border-line bg-surface-inset px-2 text-xs text-fg outline-none focus:border-brand"
                            maxLength={2200}
                            onChange={(event) => {
                              const caption = event.target.value;
                              setForm((current) => ({
                                ...current,
                                media_captions: { ...current.media_captions, [mediaId]: caption },
                              }));
                            }}
                            placeholder="Legenda do post (opcional)"
                            value={form.media_captions[mediaId] ?? item.caption ?? ""}
                          />
                        )}
                        {loops.data.can_configure && item && !item.locked && showsCover &&
                          form.cover_mode === "per_media" && item.media_type === "video" && (
                          <CoverPicker
                            compact
                            coverId={
                              mediaId in form.media_covers
                                ? form.media_covers[mediaId]
                                : (item.cover_media_id ?? null)
                            }
                            disabled={uploadCover.isPending}
                            label={`Capa de ${item.filename}`}
                            onPick={(files) => pickCover(files, mediaId)}
                            onClear={() =>
                              setForm((current) => ({
                                ...current,
                                media_covers: { ...current.media_covers, [mediaId]: null },
                              }))
                            }
                          />
                        )}
                      </span>
                      {loops.data.can_configure && (
                        <button
                          className="shrink-0 text-danger hover:text-white"
                          onClick={() =>
                            setForm((current) => ({
                              ...current,
                              media_ids: current.media_ids.filter((id) => id !== mediaId),
                            }))
                          }
                          type="button"
                        >
                          Remover
                        </button>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
          <details className="rounded-lg border border-line bg-surface-inset">
            <summary className="cursor-pointer px-3 py-3 text-sm font-medium text-fg-2">
              Configurações do loop e biblioteca de mídias
            </summary>
          <fieldset disabled={!loops.data.can_configure} className="space-y-4">
          <label className="grid gap-2 text-sm text-fg-2">
            Nome do loop
            <input
              className="min-h-10 rounded-lg border border-line bg-surface-inset px-3 text-fg outline-none focus:border-brand"
              maxLength={120}
              required
              value={form.name}
              onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
              placeholder="Ex.: Reels diários"
            />
          </label>

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="grid gap-2 text-sm text-fg-2">
              Intervalo mínimo (min)
              <input
                className="min-h-10 rounded-lg border border-line bg-surface-inset px-3 text-fg outline-none focus:border-brand"
                type="number"
                min={1}
                max={1440}
                required
                value={form.interval_min_minutes}
                onChange={(event) =>
                  setForm((current) => ({ ...current, interval_min_minutes: Number(event.target.value) }))
                }
              />
            </label>
            <label className="grid gap-2 text-sm text-fg-2">
              Intervalo máximo (min)
              <input
                className="min-h-10 rounded-lg border border-line bg-surface-inset px-3 text-fg outline-none focus:border-brand"
                type="number"
                min={form.interval_min_minutes}
                max={1440}
                required
                value={form.interval_max_minutes}
                onChange={(event) =>
                  setForm((current) => ({ ...current, interval_max_minutes: Number(event.target.value) }))
                }
              />
            </label>
          </div>
          {form.interval_max_minutes < form.interval_min_minutes && (
            <p className="text-xs text-danger" role="alert">
              O intervalo máximo precisa ser maior ou igual ao mínimo.
            </p>
          )}
          <label className="grid gap-2 text-sm text-fg-2">
            Máximo de publicações por conta por dia
            <input
              className="min-h-10 rounded-lg border border-line bg-surface-inset px-3 text-fg outline-none focus:border-brand"
              type="number"
              min={1}
              max={100}
              required
              value={form.daily_limit_per_account}
              onChange={(event) =>
                setForm((current) => ({ ...current, daily_limit_per_account: Number(event.target.value) }))
              }
            />
          </label>
          <p className="text-xs leading-5 text-muted">
            Cada conta segue sua própria sequência (vídeo 1, 2, 3… e depois recomeça) e só
            avança quando a Meta confirma a publicação. O próximo envio de cada conta é
            sorteado entre o intervalo mínimo e o máximo (fixo se forem iguais). Ao atingir o
            limite diário, a conta pausa até a meia-noite (horário de Brasília) e continua do
            próximo vídeo. O Instagram permite no máximo 100 publicações por conta em 24 h.
          </p>

          <fieldset>
            <legend className="mb-2 text-sm text-fg-2">Tipo de publicação</legend>
            <div className="flex flex-wrap gap-2">
              {([
                ["reels", "Reels (vídeo)", Video],
                ["images", "Imagem", ImageIcon],
                ["both", "Ambos", Infinity],
              ] as const).map(([value, label, Icon]) => (
                <button
                  className={`inline-flex min-h-10 items-center gap-2 rounded-lg border px-3 py-2 text-sm ${
                    form.post_type === value
                      ? "border-brand bg-brand-soft text-accent"
                      : "border-line text-muted hover:bg-surface-raised"
                  }`}
                  key={value}
                  type="button"
                  onClick={() =>
                    setForm((current) => ({
                      ...current,
                      post_type: value,
                      media_ids: current.media_ids.filter((id) => {
                        const selectedMedia = media.data?.media.find((item) => item.id === id);
                        return selectedMedia ? mediaFitsLoop(selectedMedia, value) : false;
                      }),
                    }))
                  }
                >
                  <Icon size={15} />
                  {label}
                </button>
              ))}
            </div>
          </fieldset>

          <fieldset className="space-y-3">
            <legend className="mb-2 text-sm text-fg-2">
              Pool de mídias ({form.media_ids.length} selecionadas)
            </legend>
            <div className="grid gap-3 sm:grid-cols-[1fr_2fr]">
              <label className="grid gap-2 text-sm text-fg-2">
                Legenda dos próximos arquivos enviados (opcional)
                <input
                  className="min-h-10 rounded-lg border border-line bg-surface-inset px-3 text-fg outline-none focus:border-brand"
                  maxLength={2200}
                  value={uploadCaption}
                  onChange={(event) => setUploadCaption(event.target.value)}
                  placeholder="Legenda do post"
                />
              </label>
              <label className="grid gap-2 text-sm text-fg-2">
                Enviar arquivos para este loop (JPEG ou MP4 de até 50 MB cada)
                <input
                  className="min-h-10 rounded-lg border border-line bg-surface-inset px-3 py-2 text-sm text-fg-2 file:mr-3 file:rounded file:border-0 file:bg-well file:px-3 file:py-1 file:text-fg-2"
                  type="file"
                  accept={
                    form.post_type === "reels"
                      ? "video/mp4"
                      : form.post_type === "images"
                        ? "image/jpeg"
                        : "image/jpeg,video/mp4"
                  }
                  multiple
                  disabled={
                    uploadingBatch ||
                    !loops.data.can_manage
                  }
                  onChange={(event) => {
                    const files = Array.from(event.currentTarget.files ?? []);
                    event.currentTarget.value = "";
                    if (files.length) void uploadFiles(files);
                  }}
                />
              </label>
            </div>
            <p className="text-xs text-muted">
              Adicione quantos arquivos quiser. Eles serão associados somente a este loop quando
              você salvar; a primeira publicação começa assim que houver contas e mídias.
            </p>
            {uploadingBatch && (
              <p className="text-sm text-accent">Enviando arquivos para o Storage...</p>
            )}
            {uploadValidationError && (
              <p className="rounded-lg border border-warning/30 bg-warning-soft p-3 text-sm text-warning">
                {uploadValidationError}
              </p>
            )}
            <p className="text-xs text-muted">
              Imagens aceitas: JPEG. Vídeos aceitos: MP4. Os arquivos ficam privados e o servidor
              gera uma URL temporária somente durante a publicação.
            </p>
          </fieldset>
          </fieldset>

          </details>
          {saveLoop.error && (
            <p className="rounded-lg border border-danger/30 bg-danger-soft p-3 text-sm text-danger" role="alert">
              {apiErrorMessage(saveLoop.error, "Não foi possível salvar o loop.")}
            </p>
          )}
          <button
            className="min-h-11 w-full rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-strong disabled:cursor-not-allowed disabled:opacity-50"
            type="submit"
            disabled={
              saveLoop.isPending ||
              editAccounts.isLoading ||
              Boolean(editAccounts.error) ||
              (!loops.data.can_configure && !editingId) ||
              !form.name.trim() ||
              (form.account_ids.length === 0 && form.auto_folder_ids.length === 0) ||
              form.interval_min_minutes < 1 ||
              form.interval_max_minutes < form.interval_min_minutes ||
              (showsCover && form.cover_mode === "all" && !form.cover_media_id) ||
              uploadCover.isPending ||
              !Number.isInteger(form.daily_limit_per_account) ||
              form.daily_limit_per_account < 1 ||
              form.daily_limit_per_account > 100
            }
          >
            {saveLoop.isPending
              ? "Salvando..."
              : !loops.data.can_configure
                ? "Salvar contas associadas"
                : editingId
                  ? "Salvar alterações"
                  : "Criar loop"}
          </button>
        </form>
      </Modal>

      {visibleLoops.length === 0 ? (
        <EmptyState
          message={
            loops.data.loops.length === 0
              ? "Nenhum loop configurado neste workspace."
              : loops.data.loops.every((loop) => loop.linked)
                ? "Você ainda não criou loops próprios."
                : "Não há loops nesta categoria."
          }
        />
      ) : (
        <div className="space-y-3">
          {visibleLoops.map((loop) => (
            <article
              className="cursor-pointer rounded-xl border border-line bg-surface p-4 sm:p-4"
              key={loop.id}
              onClick={(event) => {
                if ((event.target as HTMLElement).closest("button,a,input,select,textarea,details,summary,label")) return;
                toggleLoop(loop.id);
              }}
            >
              <div className="flex flex-col justify-between gap-4 sm:flex-row">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="font-semibold text-fg">{loop.name}</h3>
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs ${
                        loop.status === "active"
                          ? "bg-success-soft text-success"
                          : "bg-[#272a31] text-fg-2"
                      }`}
                    >
                      {loop.status === "active" ? "ativo" : "pausado"}
                    </span>
                    <span className="rounded-full bg-well px-2 py-0.5 text-xs text-muted">
                      {loop.repeat_media ? "Contínuo" : "Limitado"}
                    </span>
                  </div>
                  <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
                    <span className="inline-flex items-center gap-1">
                      <Clock3 size={13} />
                      {loop.interval_min_minutes === loop.interval_max_minutes
                        ? `${loop.interval_min_minutes} min entre posts`
                        : `${loop.interval_min_minutes}–${loop.interval_max_minutes} min entre posts`}
                    </span>
                    <span>até {loop.daily_limit_per_account}/dia por conta</span>
                    <span>
                      {loop.post_type === "reels"
                        ? "Reels"
                        : loop.post_type === "images"
                          ? "Imagens"
                          : "Reels e imagens"}
                    </span>
                  </p>
                  <button
                    aria-expanded={expandedLoops.includes(loop.id)}
                    className="mt-3 inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium text-accent nm-hover"
                    onClick={() => toggleLoop(loop.id)}
                    type="button"
                  >
                    <ChevronDown
                      className={`transition-transform ${expandedLoops.includes(loop.id) ? "rotate-180" : ""}`}
                      size={14}
                    />
                    {expandedLoops.includes(loop.id) ? "Ocultar contas" : "Ver contas"} ({loop.accounts_count})
                  </button>
                  {expandedLoops.includes(loop.id) && (
                    <LoopAccountsList loopId={loop.id} />
                  )}
                  <p className="mt-3 text-xs text-muted">
                    Próxima execução: {formatDate(loop.next_run_at)}
                  </p>
                  <p className="mt-1 text-xs text-success">
                    {loop.active_accounts_count}{" "}
                    {loop.active_accounts_count === 1
                      ? "conta ativa no loop"
                      : "contas ativas no loop"}
                    {" · "}
                    {loop.video_count}{" "}
                    {loop.video_count === 1 ? "vídeo no loop" : "vídeos no loop"}
                  </p>
                  <p className="mt-1 text-xs text-warning">
                    {loop.queued_publication_count}{" "}
                    {loop.queued_publication_count === 1
                      ? "vídeo na fila"
                      : "vídeos na fila"} ·{" "}
                    {loop.attempts_today_count} tentativas hoje ·{" "}
                    {loop.attempts_count} tentativas no total ·{" "}
                    {loop.published_today_count} publicados hoje ·{" "}
                    {loop.failed_today_count} falhas hoje
                  </p>
                  {loop.latest_failed_at && (
                    <p className="mt-1 text-xs text-danger">
                      Última falha: {formatDate(loop.latest_failed_at)}
                    </p>
                  )}
                  <LoopHealthPanel loopId={loop.id} />
                </div>
                {loops.data.can_manage && (
                  <div className="flex shrink-0 items-start gap-1">
                    {loops.data.can_configure && <ShareLoopButton loop={loop} />}
                    {loops.data.can_configure && (
                      <button
                        className="grid size-9 place-items-center rounded-lg border border-line text-fg-2 hover:bg-surface-raised disabled:opacity-50"
                        type="button"
                        aria-label={`Clonar ${loop.name}`}
                        title="Clonar loop"
                        disabled={cloneLoop.isPending}
                        onClick={() => cloneLoop.mutate(loop.id)}
                      >
                        <Copy size={15} />
                      </button>
                    )}
                    <button
                      className="grid size-9 place-items-center rounded-lg border border-line text-fg-2 hover:bg-surface-raised"
                      type="button"
                      aria-label={
                        loops.data.can_configure
                          ? `Editar ${loop.name}`
                          : `Associar contas a ${loop.name}`
                      }
                      onClick={() => beginEdit(loop)}
                    >
                      <Pencil size={15} />
                    </button>
                    {loops.data.can_configure && (
                    <button
                      className="grid size-9 place-items-center rounded-lg border border-line text-fg-2 hover:bg-surface-raised disabled:opacity-50"
                      type="button"
                      aria-label={loop.status === "active" ? `Pausar ${loop.name}` : `Ativar ${loop.name}`}
                      disabled={changeStatus.isPending}
                      onClick={() =>
                        changeStatus.mutate({ id: loop.id, enabled: loop.status !== "active" })
                      }
                    >
                      {loop.status === "active" ? <Pause size={15} /> : <Play size={15} />}
                    </button>
                    )}
                    {loops.data.can_delete && (
                      <button
                        className="grid size-9 place-items-center rounded-lg border border-danger/30 text-danger hover:bg-danger-soft disabled:opacity-50"
                        type="button"
                        aria-label={`Excluir ${loop.name}`}
                        disabled={deleteLoop.isPending}
                        onClick={async () => {
                          if (await confirmAction(`Excluir o loop "${loop.name}" e suas execuções pendentes?`)) {
                            deleteLoop.mutate(loop.id);
                          }
                        }}
                      >
                        <Trash2 size={15} />
                      </button>
                    )}
                  </div>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
        </div>
      )}
    </div>
  );
}

function CoverPicker({
  coverId,
  label,
  disabled,
  compact = false,
  onPick,
  onClear,
}: {
  coverId: string | null;
  label: string;
  disabled: boolean;
  compact?: boolean;
  onPick: (files: FileList | null) => void;
  onClear: () => void;
}) {
  const size = compact ? "h-12 w-9" : "h-24 w-[54px]";
  return (
    <div className="flex items-center gap-3">
      {coverId ? (
        <img
          alt={label}
          className={`${size} shrink-0 rounded border border-line object-cover`}
          src={`/api/media/${coverId}/preview`}
        />
      ) : (
        <span
          className={`${size} flex shrink-0 items-center justify-center rounded border border-dashed border-line text-muted`}
        >
          <ImageIcon size={compact ? 14 : 18} />
        </span>
      )}
      <span className="flex flex-wrap items-center gap-2 text-xs">
        <label
          className={`cursor-pointer rounded border border-line px-2 py-1 text-fg-2 hover:bg-surface-raised ${
            disabled ? "pointer-events-none opacity-50" : ""
          }`}
        >
          {coverId ? "Trocar capa" : "Escolher capa (JPEG)"}
          <input
            aria-label={label}
            accept="image/jpeg"
            className="sr-only"
            disabled={disabled}
            type="file"
            onChange={(event) => {
              onPick(event.currentTarget.files);
              event.currentTarget.value = "";
            }}
          />
        </label>
        {coverId && (
          <button className="text-danger hover:text-white" type="button" onClick={onClear}>
            Remover capa
          </button>
        )}
      </span>
    </div>
  );
}
