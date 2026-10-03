import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Clock3,
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

type LoopAccount = {
  id: string;
  username: string;
  token_expires_at: string;
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

type InstagramLoop = {
  id: string;
  name: string;
  interval_min_minutes: number;
  interval_max_minutes: number;
  daily_limit_per_account: number;
  post_type: "reels" | "images" | "both";
  repeat_media: boolean;
  status: "active" | "paused";
  next_run_at: string | null;
  last_run_at: string | null;
  accounts: LoopAccount[];
  media_ids: string[];
  waiting_for_media_count: number;
  published_today_count: number;
  failed_count: number;
  last_failure: string | null;
};

type InstagramLoopsResponse = {
  can_manage: boolean;
  loops: InstagramLoop[];
  available_accounts: LoopAccount[];
};

type LoopForm = {
  name: string;
  interval_min_minutes: number;
  interval_max_minutes: number;
  daily_limit_per_account: number;
  post_type: "reels" | "images" | "both";
  repeat_media: boolean;
  account_ids: string[];
  media_ids: string[];
};

const emptyForm: LoopForm = {
  name: "",
  interval_min_minutes: 20,
  interval_max_minutes: 40,
  daily_limit_per_account: 24,
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
  const [tab, setTab] = useState<"continuous" | "limited">("continuous");
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

  const saveLoop = useMutation({
    mutationFn: () =>
      apiRequest<InstagramLoop>(editingId ? `/api/loops/${editingId}` : "/api/loops", {
        method: editingId ? "PUT" : "POST",
        body: form,
      }),
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
  const deleteLoop = useMutation({
    mutationFn: (id: string) => apiRequest(`/api/loops/${id}`, { method: "DELETE" }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["loops"] }),
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
      (loops.data?.loops ?? []).filter((loop) =>
        tab === "continuous" ? loop.repeat_media : !loop.repeat_media,
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
    apiErrorMessage(deleteLoop.error, "Não foi possível remover o loop."),
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
      daily_limit_per_account: loop.daily_limit_per_account,
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
        {loops.data.can_manage && (
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

      <div className="rounded-lg border border-[#6b552b] bg-[#1c180e] p-4 text-sm text-[#f2d48a]">
        <p className="flex items-start gap-2">
          <AlertTriangle size={17} className="mt-0.5 shrink-0" />
          O envio ao Instagram só acontece com o worker ativo e
          <code className="mx-1 font-mono">INSTAGRAM_PUBLISHING_ENABLED=true</code>.
          Mantenha essa opção desativada até validar as credenciais e testar uma conta.
        </p>
      </div>
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
      </div>
      <p className="text-sm leading-6 text-[#94a3b8]">
        Cada loop escolhe a próxima execução aleatoriamente dentro do intervalo configurado e
        respeita o limite diário por conta. A mídia precisa estar no bucket privado e selecionada
        no pool do loop para entrar na fila de publicação.
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
              {editingId ? "Editar loop" : "Novo loop"}
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

          <div className="grid gap-4 sm:grid-cols-3">
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
            <label className="grid gap-2 text-sm text-[#cbd5e1]">
              Limite diário por conta
              <input
                className="min-h-10 rounded-lg border border-[#27334a] bg-[#090b0f] px-3 text-[#f5f7fb] outline-none focus:border-[#00c9d8]"
                type="number"
                min={1}
                max={100}
                required
                value={form.daily_limit_per_account}
                onChange={(event) =>
                  setForm({ ...form, daily_limit_per_account: Number(event.target.value) })
                }
              />
            </label>
          </div>

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
              Você pode escolher vários vídeos de uma vez, sem limite de quantidade no pool. Cada
              loop publica um vídeo por execução, seguindo o intervalo e os limites configurados.
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
            ) : (
              <div className="grid gap-2 sm:grid-cols-2">
                {media.data.media.map((item) => {
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

          <fieldset>
            <legend className="mb-2 text-sm text-[#cbd5e1]">
              Contas Instagram ({form.account_ids.length} selecionadas)
            </legend>
            {loops.data.available_accounts.length === 0 ? (
              <p className="rounded-lg border border-[#6b552b] bg-[#1c180e] p-3 text-sm text-[#f2d48a]">
                Não há contas ativas com token válido. Conecte ou reconecte uma conta no Hub de
                Contas antes de criar o loop.
              </p>
            ) : (
              <div className="grid max-h-64 gap-2 overflow-y-auto sm:grid-cols-2 lg:grid-cols-3">
                {loops.data.available_accounts.map((account) => {
                  const checked = form.account_ids.includes(account.id);
                  return (
                    <label
                      className={`flex min-h-11 cursor-pointer items-center gap-2 rounded-lg border px-3 text-sm ${
                        checked
                          ? "border-[#00c9d8] bg-[#0d3036] text-[#e7fdff]"
                          : "border-[#27334a] bg-[#090b0f] text-[#cbd5e1]"
                      }`}
                      key={account.id}
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
            )}
          </fieldset>
          <button
            className="min-h-11 w-full rounded-lg bg-[#00c9d8] px-4 py-2 text-sm font-semibold text-[#062027] hover:bg-[#42dbe5] disabled:cursor-not-allowed disabled:opacity-50"
            type="submit"
            disabled={
              saveLoop.isPending ||
              !form.name.trim() ||
              form.account_ids.length === 0 ||
              form.interval_min_minutes < 1 ||
              form.interval_max_minutes < form.interval_min_minutes
            }
          >
            {saveLoop.isPending ? "Salvando..." : editingId ? "Salvar alterações" : "Criar loop"}
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
                    <span>Limite {loop.daily_limit_per_account}/dia/conta</span>
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
                      <span
                        className="rounded bg-[#101923] px-2 py-1 text-xs text-[#cbd5e1]"
                        key={account.id}
                      >
                        @{account.username}
                      </span>
                    ))}
                  </div>
                  <p className="mt-3 text-xs text-[#94a3b8]">
                    Próxima execução: {formatDate(loop.next_run_at)}
                  </p>
                  <p className="mt-1 text-xs text-[#f2d48a]">
                    {loop.waiting_for_media_count} {loop.waiting_for_media_count === 1 ? "item" : "itens"} aguardando mídia ·{" "}
                    {loop.published_today_count} publicados hoje
                  </p>
                  {loop.failed_count > 0 && (
                    <div className="mt-1 space-y-1 text-xs text-[#f1a3ad]">
                      <p>
                        {loop.failed_count}{" "}
                        {loop.failed_count === 1 ? "publicação falhou" : "publicações falharam"}.
                        Mídias com tentativa iniciada não são reenviadas automaticamente.
                      </p>
                      {loop.last_failure && <p>Falha mais recente: {loop.last_failure}</p>}
                    </div>
                  )}
                </div>
                {loops.data.can_manage && (
                  <div className="flex shrink-0 items-start gap-2">
                    <button
                      className="grid size-9 place-items-center rounded-lg border border-[#27334a] text-[#cbd5e1] hover:bg-[#10141b]"
                      type="button"
                      aria-label={`Editar ${loop.name}`}
                      onClick={() => beginEdit(loop)}
                    >
                      <Pencil size={15} />
                    </button>
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
                  </div>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
