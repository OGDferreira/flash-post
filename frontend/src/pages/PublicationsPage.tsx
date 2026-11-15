import { useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarClock,
  Clapperboard,
  Film,
  Image as ImageIcon,
  LoaderCircle,
  Trash2,
  Upload,
} from "lucide-react";

import { apiRequest } from "@/services/api";

type Media = { id: string; filename: string; media_type: "image" | "video"; caption: string | null };
type MediaList = { media: Media[] };
type Account = { id: string; username: string; profile_folder_id: string | null; profile_picture_url: string | null; status: string };
type AccountsList = { accounts: Account[] };
type Folder = { id: string; name: string; color?: string };
type FoldersList = { folders: Folder[] };

type Publication = {
  id: string;
  media_id: string | null;
  kind: "post" | "story";
  caption: string | null;
  scheduled_for: string;
  status: string;
  targets: { total: number; queued: number; publishing: number; published: number; failed: number; canceled: number };
};
type PublicationsList = { publications: Publication[] };

const STATUS_LABEL: Record<string, string> = {
  scheduled: "Agendada", publishing: "Publicando", done: "Concluída", canceled: "Cancelada",
};

function defaultWhen(): string {
  const d = new Date(Date.now() + 60 * 60 * 1000); // +1h
  d.setSeconds(0, 0);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function PublicationsPage() {
  const cache = useQueryClient();
  const media = useQuery({ queryKey: ["instagram", "media"], queryFn: () => apiRequest<MediaList>("/api/media") });
  const accountsQuery = useQuery({ queryKey: ["instagram", "accounts"], queryFn: () => apiRequest<AccountsList>("/api/instagram/accounts") });
  const foldersQuery = useQuery({ queryKey: ["instagram", "folders"], queryFn: () => apiRequest<FoldersList>("/api/instagram/folders?include_accounts=false") });
  const list = useQuery({ queryKey: ["publications"], queryFn: () => apiRequest<PublicationsList>("/api/publications") });

  const accounts = accountsQuery.data?.accounts ?? [];
  const folders = foldersQuery.data?.folders ?? [];

  const [mediaId, setMediaId] = useState<string | null>(null);
  const [kind, setKind] = useState<"post" | "story">("post");
  const [caption, setCaption] = useState("");
  const [when, setWhen] = useState(defaultWhen);
  const [accountIds, setAccountIds] = useState<string[]>([]);
  const [folderIds, setFolderIds] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const selectedMedia = media.data?.media.find((m) => m.id === mediaId) ?? null;

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const type = file.type === "video/mp4" ? "video/mp4" : "image/jpeg";
      return apiRequest<Media>(`/api/media?filename=${encodeURIComponent(file.name)}&purpose=post`, {
        method: "POST", headers: { "Content-Type": type }, body: file,
      });
    },
    onSuccess: (m) => {
      cache.invalidateQueries({ queryKey: ["instagram", "media"] });
      setMediaId(m.id);
      setError(null);
    },
    onError: (e: unknown) => setError(e instanceof Error ? e.message : "Falha ao enviar a mídia."),
  });

  const create = useMutation({
    mutationFn: () => {
      if (!mediaId) throw new Error("Escolha uma mídia.");
      if (accountIds.length === 0 && folderIds.length === 0) throw new Error("Escolha pelo menos uma conta ou pasta.");
      const iso = new Date(when).toISOString();
      if (new Date(when).getTime() <= Date.now()) throw new Error("A data precisa ser no futuro.");
      return apiRequest<Publication>("/api/publications", {
        method: "POST",
        body: { media_id: mediaId, kind, caption: kind === "post" ? caption : null, scheduled_for: iso, account_ids: accountIds, folder_ids: folderIds },
      });
    },
    onSuccess: () => {
      cache.invalidateQueries({ queryKey: ["publications"] });
      setMediaId(null); setCaption(""); setAccountIds([]); setFolderIds([]); setWhen(defaultWhen()); setError(null);
    },
    onError: (e: unknown) => setError(e instanceof Error ? e.message : "Não foi possível agendar."),
  });

  const cancel = useMutation({
    mutationFn: (id: string) => apiRequest(`/api/publications/${id}`, { method: "DELETE" }),
    onSuccess: () => cache.invalidateQueries({ queryKey: ["publications"] }),
  });

  const toggle = (arr: string[], id: string) => (arr.includes(id) ? arr.filter((x) => x !== id) : [...arr, id]);
  const reach = useMemo(() => {
    const direct = new Set(accountIds);
    accounts.forEach((a) => { if (a.profile_folder_id && folderIds.includes(a.profile_folder_id)) direct.add(a.id); });
    return direct.size;
  }, [accountIds, folderIds, accounts]);

  return (
    <div className="space-y-4">
      <div className="mt-2">
        <h2 className="text-2xl font-semibold tracking-[-0.045em] text-fg sm:text-3xl">Publicações</h2>
        <p className="mt-1 text-sm text-muted">Agende um post no feed ou um story (foto ou vídeo) para várias contas ou pastas, sem ser em loop.</p>
      </div>

      <section className="glass-panel space-y-4 p-4 sm:p-5">
        {/* Kind */}
        <div className="inline-flex rounded-lg border border-line p-0.5">
          {(["post", "story"] as const).map((k) => (
            <button key={k} type="button" onClick={() => setKind(k)}
              className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium ${kind === k ? "bg-brand text-white" : "text-muted hover:text-fg"}`}>
              {k === "post" ? <ImageIcon size={15} /> : <Clapperboard size={15} />} {k === "post" ? "Post no feed" : "Story"}
            </button>
          ))}
        </div>

        {/* Media picker */}
        <div>
          <div className="mb-1.5 flex items-center justify-between">
            <span className="text-xs font-medium text-muted">Mídia (foto ou vídeo)</span>
            <button type="button" onClick={() => fileRef.current?.click()} disabled={upload.isPending}
              className="inline-flex items-center gap-1.5 text-xs font-medium text-accent hover:text-white">
              {upload.isPending ? <LoaderCircle size={13} className="animate-spin" /> : <Upload size={13} />} Enviar nova
            </button>
            <input ref={fileRef} type="file" accept="image/jpeg,video/mp4" className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f); e.target.value = ""; }} />
          </div>
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-5 lg:grid-cols-6">
            {media.data?.media.map((m) => (
              <button key={m.id} type="button" onClick={() => setMediaId(m.id)}
                className={`relative aspect-square overflow-hidden rounded-lg border ${mediaId === m.id ? "border-brand ring-2 ring-brand" : "border-line"}`}>
                {m.media_type === "image" ? (
                  <img src={`/api/media/${m.id}/preview`} alt={m.filename} className="h-full w-full object-cover" loading="lazy" />
                ) : (
                  <span className="grid h-full w-full place-items-center bg-surface-inset text-muted"><Film size={20} /></span>
                )}
              </button>
            ))}
            {media.data && media.data.media.length === 0 && <p className="col-span-full text-sm text-muted">Nenhuma mídia ainda. Envie uma acima.</p>}
          </div>
          {selectedMedia && <p className="mt-1 text-[11px] text-muted">Selecionada: {selectedMedia.filename}</p>}
        </div>

        {/* Caption (post only) */}
        {kind === "post" && (
          <label className="block text-xs font-medium text-muted">
            Legenda (opcional)
            <textarea className="mt-1 block w-full rounded-lg border border-line bg-surface-inset px-3 py-2 text-sm text-fg outline-none focus:border-brand"
              rows={2} maxLength={2200} value={caption} onChange={(e) => setCaption(e.target.value)} placeholder="Escreva a legenda do post..." />
          </label>
        )}

        {/* When */}
        <label className="block text-xs font-medium text-muted">
          Data e hora
          <input type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)}
            className="mt-1 block h-10 w-full rounded-lg border border-line bg-surface-inset px-3 text-sm text-fg outline-none focus:border-brand sm:w-72" />
        </label>

        {/* Targets */}
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <span className="text-xs font-medium text-muted">Contas</span>
            <div className="mt-1 max-h-48 space-y-1 overflow-y-auto rounded-lg border border-line p-2">
              {accounts.map((a) => (
                <label key={a.id} className="flex items-center gap-2 rounded-md px-2 py-1 text-sm text-fg hover:bg-surface-inset">
                  <input type="checkbox" checked={accountIds.includes(a.id)} onChange={() => setAccountIds((prev) => toggle(prev, a.id))} />
                  @{a.username}
                </label>
              ))}
              {accounts.length === 0 && <p className="px-2 text-xs text-muted">Nenhuma conta conectada.</p>}
            </div>
          </div>
          <div>
            <span className="text-xs font-medium text-muted">Pastas</span>
            <div className="mt-1 max-h-48 space-y-1 overflow-y-auto rounded-lg border border-line p-2">
              {folders.map((f) => (
                <label key={f.id} className="flex items-center gap-2 rounded-md px-2 py-1 text-sm text-fg hover:bg-surface-inset">
                  <input type="checkbox" checked={folderIds.includes(f.id)} onChange={() => setFolderIds((prev) => toggle(prev, f.id))} />
                  {f.name}
                </label>
              ))}
              {folders.length === 0 && <p className="px-2 text-xs text-muted">Nenhuma pasta.</p>}
            </div>
          </div>
        </div>

        {error && <p className="text-sm text-danger">{error}</p>}

        <div className="flex items-center justify-between gap-3">
          <span className="text-xs text-muted">{reach} conta(s) vão receber</span>
          <button type="button" disabled={create.isPending || !mediaId} onClick={() => create.mutate()}
            className="inline-flex h-10 items-center gap-2 rounded-lg bg-brand px-5 text-sm font-semibold text-white disabled:opacity-60">
            {create.isPending ? <LoaderCircle size={15} className="animate-spin" /> : <CalendarClock size={16} />} Agendar
          </button>
        </div>
      </section>

      {/* List */}
      <section className="glass-panel p-4 sm:p-5">
        <h3 className="text-base font-semibold text-fg">Agendadas</h3>
        <div className="mt-3 space-y-2">
          {list.isLoading && <p className="text-sm text-muted">Carregando...</p>}
          {list.data?.publications.map((p) => (
            <div key={p.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-line bg-surface-inset px-3 py-2 text-sm">
              <div className="min-w-0">
                <span className="flex items-center gap-1.5 font-medium text-fg">
                  {p.kind === "story" ? <Clapperboard size={14} /> : <ImageIcon size={14} />}
                  {p.kind === "story" ? "Story" : "Post"} · {new Date(p.scheduled_for).toLocaleString("pt-BR")}
                </span>
                <span className="text-xs text-muted">
                  {STATUS_LABEL[p.status] ?? p.status} · {p.targets.published}/{p.targets.total} publicadas
                  {p.targets.failed > 0 ? ` · ${p.targets.failed} falharam` : ""}
                </span>
              </div>
              {(p.status === "scheduled" || p.status === "publishing") && (
                <button type="button" onClick={() => { if (confirm("Cancelar esta publicação agendada?")) cancel.mutate(p.id); }}
                  className="inline-flex items-center gap-1 rounded-lg border border-line px-2 py-1 text-xs text-danger hover:border-danger">
                  <Trash2 size={13} /> Cancelar
                </button>
              )}
            </div>
          ))}
          {list.data && list.data.publications.length === 0 && <p className="text-sm text-muted">Nenhuma publicação agendada.</p>}
        </div>
      </section>
    </div>
  );
}

export default PublicationsPage;
