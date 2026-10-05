import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
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
import { ApiError, apiRequest } from "@/services/api";
import {
  formatAccountConnectedAt,
  formatConnectedDuration,
} from "@/features/instagram/accountDates";

type LoopAccount = {
  id: string;
  profile_folder_id: string | null;
  username: string;
  token_expires_at: string;
  connected_at: string;
  error_at: string | null;
  status: "connected" | "disconnected" | "error";
};

type InstagramMedia = {
  id: string;
  filename: string;
  mime_type: string;
  media_type: "image" | "video";
  size_bytes: number;
  caption: string | null;
  created_at: string;
};

type InstagramMediaResponse = {
  can_manage: boolean;
  media: InstagramMedia[];
};

type InstagramFoldersResponse = {
  folders: { id: string; name: string; color: string }[];
};

type InstagramLoop = {
  id: string;
  name: string;
  interval_min_minutes: number;
  interval_max_minutes: number;
  post_type: "reels" | "images" | "both";
  repeat_media: boolean;
  status: "active" | "paused";
  next_run_at: string | null;
  last_run_at: string | null;
  accounts: LoopAccount[];
  media_ids: string[];
  media_names: string[];
  media_count: number;
  waiting_for_media_count: number;
  published_today_count: number;
  failed_count: number;
};

type InstagramLoopsResponse = {
  can_manage: boolean;
  can_configure: boolean;
  can_delete: boolean;
  publishing_enabled: boolean;
  loops: InstagramLoop[];
  available_accounts: LoopAccount[];
};

type PublicationFailure = {
  id: string;
  loop_name: string;
  account_username: string;
  media_filename: string | null;
  scheduled_for: string;
  updated_at: string;
  attempts: number;
  error: string;
};

type PublicationFailuresResponse = {
  failures: PublicationFailure[];
};

type LoopForm = {
  name: string;
  interval_min_minutes: number;
  interval_max_minutes: number;
  post_type: "reels" | "images" | "both";
  repeat_media: boolean;
  account_ids: string[];
  media_ids: string[];
};

const emptyForm: LoopForm = {
  name: "",
  interval_min_minutes: 20,
  interval_max_minutes: 40,
  post_type: "reels",
  repeat_media: true,
  account_ids: [],
  media_ids: [],
};

const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;

function formatDate(value: string | null): string {
  if (!value) return "Aguardando execução do agendador";
  return new Date(value).toLocaleString("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "America/Sao_Paulo",
  });
}

function apiErrorMessage(error: unknown, fallback: string): string | null {
  if (!error) return null;
  return error instanceof ApiError ? error.message : fallback;
}

function mediaFitsLoop(media: InstagramMedia, postType: LoopForm["post_type"]): boolean {
  return (
    postType === "both" ||
    (postType === "reels" && media.media_type === "video") ||
    (postType === "images" && media.media_type === "image")
  );
}

function fileFitsLoop(file: File, postType: LoopForm["post_type"]): boolean {
  return (
    (file.type === "video/mp4" && (postType === "reels" || postType === "both")) ||
    (file.type === "image/jpeg" && (postType === "images" || postType === "both"))
  );
}

function formatFileSize(sizeBytes: number): string {
  return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function LoopsPage() {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<"continuous" | "limited" | "errors">("continuous");
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<LoopForm>(emptyForm);
  const [uploadCaption, setUploadCaption] = useState("");
  const [uploadValidationError, setUploadValidationError] = useState<string | null>(null);
  const [uploadingBatch, setUploadingBatch] = useState(false);
  const loops = useQuery({
    queryKey: ["loops"],
    queryFn: () => apiRequest<InstagramLoopsResponse>("/api/loops"),
    refetchInterval: 60_000,
    retry: false,
  });
  const media = useQuery({
    queryKey: ["instagram-media"],
    queryFn: () => apiRequest<InstagramMediaResponse>("/api/media"),
    retry: false,
  });
  const folders = useQuery({
    queryKey: ["instagram", "folders"],
    queryFn: () => apiRequest<InstagramFoldersResponse>("/api/instagram/folders"),
    retry: false,
  });
  const failures = useQuery({
    queryKey: ["loops", "failures"],
    queryFn: () => apiRequest<PublicationFailuresResponse>("/api/loops/failures"),
    enabled: tab === "errors" && loops.data?.can_configure === true,
    refetchInterval: 60_000,
    retry: false,
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
  const deleteMedia = useMutation({
    mutationFn: (id: string) => apiRequest(`/api/media/${id}`, { method: "DELETE" }),
    onSuccess: (_result, id) => {
      setForm((current) => ({
        ...current,
        media_ids: current.media_ids.filter((mediaId) => mediaId !== id),
      }));
      void queryClient.invalidateQueries({ queryKey: ["instagram-media"] });
    },
  });

  const visibleLoops = useMemo(
    () =>
      (loops.data?.loops ?? []).filter(
        (loop) => tab !== "errors" && (tab === "continuous" ? loop.repeat_media : !loop.repeat_media),
      ),
    [loops.data?.loops, tab],
  );
  const mediaAssignedToOtherLoops = new Set(
    (loops.data?.loops ?? [])
      .filter((loop) => loop.id !== editingId)
      .flatMap((loop) => loop.media_ids),
  );
  const selectableMedia = (media.data?.media ?? []).filter(
    (item) => !mediaAssignedToOtherLoops.has(item.id) || form.media_ids.includes(item.id),
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
    apiErrorMessage(deleteMedia.error, "Não foi possível remover a mídia."),
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
    setForm({
      name: loop.name,
      interval_min_minutes: loop.interval_min_minutes,
      interval_max_minutes: loop.interval_max_minutes,
      post_type: loop.post_type,
      repeat_media: loop.repeat_media,
      media_ids: loop.media_ids,
      account_ids: loop.accounts
        .filter((account) =>
          loops.data?.available_accounts.some((available) => available.id === account.id),
        )
        .map((account) => account.id),
    });
    setFormOpen(true);
    saveLoop.reset();
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-[#7186ff]">
            Publicação automatizada
          </p>
          <h2 className="mt-2 flex items-center gap-2 text-2xl font-semibold tracking-[-0.045em] text-[#f5f7fb] sm:text-3xl">
            <Infinity size={27} className="text-[#00c9d8]" />
            Loops
          </h2>
        </div>
        {loops.data.can_configure && (
          <button
            className="inline-flex min-h-10 items-center gap-2 rounded-lg bg-[#00c9d8] px-4 py-2 text-sm font-semibold text-[#062027] hover:bg-[#42dbe5]"
            type="button"
            onClick={() => {
              setEditingId(null);
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

      {!loops.data.publishing_enabled ? (
        <div className="rounded-lg border border-[#6b552b] bg-[#1c180e] p-4 text-sm text-[#f2d48a]">
          <p className="flex items-start gap-2">
            <AlertTriangle size={17} className="mt-0.5 shrink-0" />
            As publicações automáticas estão desativadas no servidor. Configure
            {" "}<code className="font-mono">INSTAGRAM_PUBLISHING_ENABLED=true</code>
            {" "}no serviço Web do Render e reinicie ou reimplante o serviço para habilitá-las.
          </p>
        </div>
      ) : (
        <div className="rounded-lg border border-[#23513e] bg-[#0e1b17] p-4 text-sm text-[#9de0c0]">
          Publicações automáticas habilitadas. O worker precisa estar ativo para processar a fila.
        </div>
      )}
      {mutationError && <ErrorState message={mutationError} />}
      {!loops.data.can_manage && (
        <p className="rounded-lg border border-[#27334a] bg-[#10141b] px-4 py-3 text-sm text-[#aeb9ce]">
          Você pode consultar os loops. Somente o OWNER pode configurá-los.
        </p>
      )}

      <div className="flex gap-1 border-b border-[#27334a]">
        {([
          ["continuous", "Contínuos"],
          ["limited", "Limitados"],
        ] as const).map(([value, label]) => (
          <button
            className={`border-b-2 px-4 py-3 text-sm ${
              tab === value
                ? "border-[#00c9d8] font-medium text-white"
                : "border-transparent text-[#94a3b8] hover:text-white"
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
              ? "border-[#00c9d8] font-medium text-white"
              : "border-transparent text-[#94a3b8] hover:text-white"
          }`}
          type="button"
          onClick={() => setTab("errors")}
        >
          Erros ({loops.data.loops.reduce((total, loop) => total + loop.failed_count, 0)})
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
        <section aria-label="Log de erros de publicação" className="space-y-3">
          {failures.data.failures.map((failure) => (
            <article
              className="space-y-2 rounded-xl border border-[#47252d] bg-[#130e11] p-4"
              key={failure.id}
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="font-medium text-[#f5f7fb]">
                  @{failure.account_username} · {failure.loop_name}
                </h3>
                <time className="text-xs text-[#94a3b8]">
                  {formatDate(failure.updated_at)}
                </time>
              </div>
              <p className="text-xs text-[#94a3b8]">
                {failure.media_filename ?? "Mídia não identificada"} ·{" "}
                {failure.attempts} {failure.attempts === 1 ? "tentativa" : "tentativas"}
              </p>
              <p className="break-words text-sm leading-6 text-[#f1a3ad]">{failure.error}</p>
            </article>
          ))}
        </section>
        )
      ) : (
        <div className="space-y-6">
      <p className="text-sm leading-6 text-[#94a3b8]">
        Cada loop escolhe a próxima execução aleatoriamente dentro do intervalo configurado e
        usa uma lista de mídias independente. A primeira publicação entra na fila assim que o loop
        é criado com contas e mídias; o intervalo controla as publicações seguintes.
      </p>

      {formOpen && loops.data.can_manage && (
        <form
          className="space-y-5 rounded-xl border border-[#27334a] bg-[#0d1015] p-5 sm:p-6"
          onSubmit={(event) => {
            event.preventDefault();
            saveLoop.mutate();
          }}
        >
          <div className="flex items-center justify-between">
            <h3 className="font-medium text-[#f5f7fb]">
              {!loops.data.can_configure && editingId
                ? "Associar contas ao loop"
                : editingId
                  ? "Editar loop"
                  : "Novo loop"}
            </h3>
            <button
              className="text-xs text-[#94a3b8] hover:text-white"
              type="button"
              onClick={() => {
                setFormOpen(false);
                setEditingId(null);
                setForm(emptyForm);
              }}
            >
              Cancelar
            </button>
          </div>
          <fieldset className="space-y-3 rounded-lg border border-[#27334a] bg-[#090b0f] p-3">
            <legend className="px-1 text-sm font-medium text-[#cbd5e1]">
              Contas Instagram ({form.account_ids.length} selecionadas)
            </legend>
            {loops.data.available_accounts.length === 0 ? (
              <p className="text-sm text-[#f2d48a]">
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
                    accounts: loops.data.available_accounts.filter(
                      (account) => account.profile_folder_id === folder.id,
                    ),
                  })),
                  {
                    id: "unassigned",
                    label: "Sem pasta",
                    color: "#64748b",
                    accounts: loops.data.available_accounts.filter(
                      (account) => !account.profile_folder_id,
                    ),
                  },
                ]
                  .filter((folder) => folder.accounts.length > 0)
                  .map((folder) => (
                    <section key={folder.id}>
                      <h4 className="mb-2 flex items-center gap-2 text-xs text-[#94a3b8]">
                        <Folder size={13} style={{ color: folder.color }} />
                        {folder.label} ({folder.accounts.length})
                      </h4>
                      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                        {folder.accounts.map((account) => {
                          const checked = form.account_ids.includes(account.id);
                          return (
                            <label
                              className={`flex min-h-10 cursor-pointer items-center gap-2 rounded-lg border px-3 text-xs ${
                                checked
                                  ? "border-[#00c9d8] bg-[#0d3036] text-[#e7fdff]"
                                  : "border-[#27334a] text-[#cbd5e1]"
                              }`}
                              key={account.id}
                              style={checked ? undefined : { borderColor: `${folder.color}66` }}
                            >
                              <input
                                className="accent-[#00c9d8]"
                                type="checkbox"
                                checked={checked}
                                onChange={() =>
                                  setForm({
                                    ...form,
                                    account_ids: checked
                                      ? form.account_ids.filter((id) => id !== account.id)
                                      : [...form.account_ids, account.id],
                                  })
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
          <section className="space-y-2 rounded-lg border border-[#27334a] bg-[#090b0f] p-3">
            <h4 className="flex items-center gap-2 text-sm font-medium text-[#cbd5e1]">
              Mídias atuais na pool ({form.media_ids.length})
            </h4>
            {form.media_ids.length === 0 ? (
              <p className="text-xs text-[#94a3b8]">Nenhuma mídia selecionada para este loop.</p>
            ) : (
              <ul className="max-h-48 space-y-1 overflow-y-auto">
                {form.media_ids.map((mediaId) => {
                  const item = media.data?.media.find((entry) => entry.id === mediaId);
                  return (
                    <li
                      className="flex items-center justify-between gap-3 rounded border border-[#202838] px-2 py-1.5 text-xs text-[#cbd5e1]"
                      key={mediaId}
                    >
                      <span className="truncate">{item?.filename ?? "Arquivo indisponível"}</span>
                      {loops.data.can_configure && (
                        <button
                          className="shrink-0 text-[#f1a3ad] hover:text-white"
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
          <details className="rounded-lg border border-[#27334a] bg-[#090b0f]">
            <summary className="cursor-pointer px-3 py-3 text-sm font-medium text-[#cbd5e1]">
              Configurações do loop e biblioteca de mídias
            </summary>
          <fieldset disabled={!loops.data.can_configure} className="space-y-5">
          <label className="grid gap-2 text-sm text-[#cbd5e1]">
            Nome do loop
            <input
              className="min-h-10 rounded-lg border border-[#27334a] bg-[#090b0f] px-3 text-[#f5f7fb] outline-none focus:border-[#00c9d8]"
              maxLength={120}
              required
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
              placeholder="Ex.: Reels diários"
            />
          </label>

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="grid gap-2 text-sm text-[#cbd5e1]">
              Intervalo mínimo (min)
              <input
                className="min-h-10 rounded-lg border border-[#27334a] bg-[#090b0f] px-3 text-[#f5f7fb] outline-none focus:border-[#00c9d8]"
                type="number"
                min={1}
                max={1440}
                required
                value={form.interval_min_minutes}
                onChange={(event) =>
                  setForm({ ...form, interval_min_minutes: Number(event.target.value) })
                }
              />
            </label>
            <label className="grid gap-2 text-sm text-[#cbd5e1]">
              Intervalo máximo (min)
              <input
                className="min-h-10 rounded-lg border border-[#27334a] bg-[#090b0f] px-3 text-[#f5f7fb] outline-none focus:border-[#00c9d8]"
                type="number"
                min={form.interval_min_minutes}
                max={1440}
                required
                value={form.interval_max_minutes}
                onChange={(event) =>
                  setForm({ ...form, interval_max_minutes: Number(event.target.value) })
                }
              />
            </label>
          </div>
          <p className="text-xs leading-5 text-[#78839b]">
            Os intervalos são contados como tempo decorrido (independente do fuso do
            servidor); os horários da próxima execução são exibidos no horário de
            Brasília (America/Sao_Paulo).
          </p>

          <fieldset>
            <legend className="mb-2 text-sm text-[#cbd5e1]">Tipo de publicação</legend>
            <div className="flex flex-wrap gap-2">
              {([
                ["reels", "Reels (vídeo)", Video],
                ["images", "Imagem", ImageIcon],
                ["both", "Ambos", Infinity],
              ] as const).map(([value, label, Icon]) => (
                <button
                  className={`inline-flex min-h-10 items-center gap-2 rounded-lg border px-3 py-2 text-sm ${
                    form.post_type === value
                      ? "border-[#00c9d8] bg-[#0d3036] text-[#8af2fa]"
                      : "border-[#27334a] text-[#94a3b8] hover:bg-[#10141b]"
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
            <legend className="mb-2 text-sm text-[#cbd5e1]">
              Pool de mídias ({form.media_ids.length} selecionadas)
            </legend>
            <div className="grid gap-3 sm:grid-cols-[1fr_2fr]">
              <label className="grid gap-2 text-sm text-[#cbd5e1]">
                Legenda para esta mídia (opcional)
                <input
                  className="min-h-10 rounded-lg border border-[#27334a] bg-[#090b0f] px-3 text-[#f5f7fb] outline-none focus:border-[#00c9d8]"
                  maxLength={2200}
                  value={uploadCaption}
                  onChange={(event) => setUploadCaption(event.target.value)}
                  placeholder="Legenda do post"
                />
              </label>
              <label className="grid gap-2 text-sm text-[#cbd5e1]">
                Enviar arquivos para este loop (JPEG ou MP4 de até 50 MB cada)
                <input
                  className="min-h-10 rounded-lg border border-[#27334a] bg-[#090b0f] px-3 py-2 text-sm text-[#cbd5e1] file:mr-3 file:rounded file:border-0 file:bg-[#17202b] file:px-3 file:py-1 file:text-[#cbd5e1]"
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
            <p className="text-xs text-[#94a3b8]">
              Adicione quantos arquivos quiser. Eles serão associados somente a este loop quando
              você salvar; a primeira publicação começa assim que houver contas e mídias.
            </p>
            {uploadingBatch && (
              <p className="text-sm text-[#8af2fa]">Enviando arquivos para o Storage...</p>
            )}
            {uploadValidationError && (
              <p className="rounded-lg border border-[#6b552b] bg-[#1c180e] p-3 text-sm text-[#f2d48a]">
                {uploadValidationError}
              </p>
            )}
            <p className="text-xs text-[#94a3b8]">
              Imagens aceitas: JPEG. Vídeos aceitos: MP4. Os arquivos ficam privados e o servidor
              gera uma URL temporária somente durante a publicação.
            </p>
            {media.isLoading ? (
              <p className="text-sm text-[#94a3b8]">Carregando mídias...</p>
            ) : media.error || !media.data ? (
              <p className="rounded-lg border border-[#47252d] bg-[#1a1013] p-3 text-sm text-[#f1a3ad]">
                Não foi possível carregar as mídias deste workspace.
              </p>
            ) : media.data.media.length === 0 ? (
              <p className="rounded-lg border border-[#27334a] bg-[#090b0f] p-3 text-sm text-[#94a3b8]">
                Nenhuma mídia enviada. Envie um arquivo para começar a montar o pool.
              </p>
            ) : selectableMedia.length === 0 ? (
              <p className="rounded-lg border border-[#27334a] bg-[#090b0f] p-3 text-sm text-[#94a3b8]">
                Todas as mídias já pertencem a outros loops. Clone um loop para reutilizar as mídias dele.
              </p>
            ) : (
              <div className="grid gap-2 sm:grid-cols-2">
                {selectableMedia.map((item) => {
                  const checked = form.media_ids.includes(item.id);
                  const compatible = mediaFitsLoop(item, form.post_type);
                  return (
                    <div
                      className={`flex items-center gap-3 rounded-lg border p-3 ${
                        checked
                          ? "border-[#00c9d8] bg-[#0d3036]"
                          : "border-[#27334a] bg-[#090b0f]"
                      }`}
                      key={item.id}
                    >
                      <input
                        className="accent-[#00c9d8]"
                        type="checkbox"
                        checked={checked}
                        disabled={
                          !compatible ||
                          !loops.data.can_manage
                        }
                        aria-label={`Selecionar ${item.filename}`}
                        onChange={() =>
                          setForm((current) => ({
                            ...current,
                            media_ids: checked
                              ? current.media_ids.filter((id) => id !== item.id)
                              : [...current.media_ids, item.id],
                          }))
                        }
                      />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm text-[#f5f7fb]">{item.filename}</p>
                        <p className="text-xs text-[#94a3b8]">
                          {item.media_type === "video" ? "MP4" : "JPEG"} · {formatFileSize(item.size_bytes)}
                          {!compatible && " · incompatível com o tipo selecionado"}
                        </p>
                      </div>
                      {loops.data.can_manage && (
                        <button
                          className="grid size-8 shrink-0 place-items-center rounded border border-[#47252d] text-[#f1a3ad] hover:bg-[#1a1013] disabled:opacity-50"
                          type="button"
                          aria-label={`Excluir mídia ${item.filename}`}
                          disabled={deleteMedia.isPending}
                          onClick={() => {
                            if (window.confirm(`Excluir a mídia "${item.filename}"?`)) {
                              deleteMedia.mutate(item.id);
                            }
                          }}
                        >
                          <Trash2 size={14} />
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </fieldset>

          <label className="flex cursor-pointer items-center gap-3 rounded-lg border border-[#27334a] bg-[#090b0f] p-3 text-sm text-[#cbd5e1]">
            <input
              className="size-4 accent-[#00c9d8]"
              type="checkbox"
              checked={!form.repeat_media}
              onChange={(event) => setForm({ ...form, repeat_media: !event.target.checked })}
            />
            Limitado: não repetir mídias
          </label>
          </fieldset>

          </details>
          <button
            className="min-h-11 w-full rounded-lg bg-[#00c9d8] px-4 py-2 text-sm font-semibold text-[#062027] hover:bg-[#42dbe5] disabled:cursor-not-allowed disabled:opacity-50"
            type="submit"
            disabled={
              saveLoop.isPending ||
              (!loops.data.can_configure && !editingId) ||
              !form.name.trim() ||
              form.account_ids.length === 0 ||
              form.interval_min_minutes < 1 ||
              form.interval_max_minutes < form.interval_min_minutes
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
      )}

      {visibleLoops.length === 0 ? (
        <EmptyState
          message={
            loops.data.loops.length === 0
              ? "Nenhum loop configurado neste workspace."
              : "Não há loops nesta categoria."
          }
        />
      ) : (
        <div className="space-y-3">
          {visibleLoops.map((loop) => (
            <article
              className="rounded-xl border border-[#27334a] bg-[#0d1015] p-4 sm:p-5"
              key={loop.id}
            >
              <div className="flex flex-col justify-between gap-4 sm:flex-row">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="font-semibold text-[#f5f7fb]">{loop.name}</h3>
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs ${
                        loop.status === "active"
                          ? "bg-[#123d2c] text-[#9de0c0]"
                          : "bg-[#272a31] text-[#aeb9ce]"
                      }`}
                    >
                      {loop.status === "active" ? "ativo" : "pausado"}
                    </span>
                    <span className="rounded-full bg-[#17202b] px-2 py-0.5 text-xs text-[#94a3b8]">
                      {loop.repeat_media ? "Contínuo" : "Limitado"}
                    </span>
                  </div>
                  <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-[#94a3b8]">
                    <span className="inline-flex items-center gap-1">
                      <Clock3 size={13} />
                      {loop.interval_min_minutes}–{loop.interval_max_minutes} min entre posts
                    </span>
                    <span>
                      {loop.post_type === "reels"
                        ? "Reels"
                        : loop.post_type === "images"
                          ? "Imagens"
                          : "Reels e imagens"}
                    </span>
                  </p>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {loop.accounts.map((account) => (
                      <div
                        className="rounded bg-[#101923] px-2 py-1 text-xs text-[#cbd5e1]"
                        key={account.id}
                      >
                        <p>@{account.username}</p>
                        <p className="mt-0.5 text-[10px] text-[#94a3b8]">
                          Conectada em {formatAccountConnectedAt(account.connected_at)}
                        </p>
                        {account.status === "error" && (
                          <p className="mt-0.5 text-[10px] text-[#f1a3ad]">
                            Duração antes do erro:{" "}
                            {formatConnectedDuration(account.connected_at, account.error_at)}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                  <p className="mt-3 text-xs text-[#94a3b8]">
                    Próxima execução: {formatDate(loop.next_run_at)}
                  </p>
                  <p className="mt-1 text-xs text-[#f2d48a]">
                    {loop.waiting_for_media_count}{" "}
                    {loop.waiting_for_media_count === 1
                      ? "publicação aguardando mídia"
                      : "publicações aguardando mídia"} ·{" "}
                    {loop.published_today_count} publicados hoje · Falhas: {loop.failed_count}
                  </p>
                </div>
                {loops.data.can_manage && (
                  <div className="flex shrink-0 items-start gap-2">
                    {loops.data.can_configure && (
                      <button
                        className="grid size-9 place-items-center rounded-lg border border-[#27334a] text-[#cbd5e1] hover:bg-[#10141b] disabled:opacity-50"
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
                      className="grid size-9 place-items-center rounded-lg border border-[#27334a] text-[#cbd5e1] hover:bg-[#10141b]"
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
                      className="grid size-9 place-items-center rounded-lg border border-[#27334a] text-[#cbd5e1] hover:bg-[#10141b] disabled:opacity-50"
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
                        className="grid size-9 place-items-center rounded-lg border border-[#47252d] text-[#f1a3ad] hover:bg-[#1a1013] disabled:opacity-50"
                        type="button"
                        aria-label={`Excluir ${loop.name}`}
                        disabled={deleteLoop.isPending}
                        onClick={() => {
                          if (window.confirm(`Excluir o loop "${loop.name}" e suas execuções pendentes?`)) {
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
