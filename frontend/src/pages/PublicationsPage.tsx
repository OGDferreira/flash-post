import { useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarClock,
  ChevronLeft,
  ChevronRight,
  Clapperboard,
  Film,
  Image as ImageIcon,
  LoaderCircle,
  MessageCircle,
  Plus,
  Trash2,
  Upload,
  X,
} from "lucide-react";

import { apiRequest } from "@/services/api";

type Media = { id: string; filename: string; media_type: "image" | "video"; caption: string | null };
type MediaList = { media: Media[] };
type Account = { id: string; username: string; profile_folder_id: string | null; profile_picture_url: string | null; status: string };
type AccountsList = { accounts: Account[] };
type Folder = { id: string; name: string; color?: string };
type FoldersList = { folders: Folder[] };
type AutomationLite = { id: string; name: string; trigger_type: "comment" | "dm" };
type AutomationsList = { automations: AutomationLite[] };

type TargetItem = { account_id: string; username: string; status: string; published_media_id: string | null };
type Publication = {
  id: string;
  media_id: string | null;
  thumbnail_media_id: string | null;
  automation_id: string | null;
  kind: "post" | "story";
  caption: string | null;
  scheduled_for: string;
  status: string;
  targets: {
    total: number; queued: number; publishing: number; published: number; failed: number; canceled: number;
    items: TargetItem[];
  };
};
type PublicationsList = { publications: Publication[] };

const TARGET_LABEL: Record<string, string> = {
  queued: "na fila", publishing: "publicando", published: "publicada", failed: "falhou", canceled: "cancelada",
};
const TARGET_DOT: Record<string, string> = {
  queued: "bg-muted", publishing: "bg-amber-400", published: "bg-success", failed: "bg-danger", canceled: "bg-line",
};
const WEEKDAYS = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];

function dayKey(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** The 6-week grid (Sunday-start) that covers `month`. */
function monthGrid(month: Date): Date[] {
  const first = new Date(month.getFullYear(), month.getMonth(), 1);
  const start = new Date(first);
  start.setDate(first.getDate() - first.getDay());
  return Array.from({ length: 42 }, (_, i) => {
    const d = new Date(start);
    d.setDate(start.getDate() + i);
    return d;
  });
}

export function PublicationsPage() {
  const cache = useQueryClient();
  const list = useQuery({ queryKey: ["publications"], queryFn: () => apiRequest<PublicationsList>("/api/publications") });

  const [month, setMonth] = useState(() => new Date(new Date().getFullYear(), new Date().getMonth(), 1));
  const [selectedDay, setSelectedDay] = useState<string | null>(() => dayKey(new Date()));
  const [selectedAccount, setSelectedAccount] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);

  const cancel = useMutation({
    mutationFn: (id: string) => apiRequest(`/api/publications/${id}`, { method: "DELETE" }),
    onSuccess: () => cache.invalidateQueries({ queryKey: ["publications"] }),
  });

  const pubs = list.data?.publications ?? [];

  // day -> publications that day
  const byDay = useMemo(() => {
    const map = new Map<string, Publication[]>();
    for (const p of pubs) {
      const k = dayKey(new Date(p.scheduled_for));
      (map.get(k) ?? map.set(k, []).get(k)!).push(p);
    }
    return map;
  }, [pubs]);

  // For the selected day: account -> [{ pub, target }]
  const dayAccounts = useMemo(() => {
    if (!selectedDay) return [];
    const dayPubs = byDay.get(selectedDay) ?? [];
    const map = new Map<string, { username: string; rows: { pub: Publication; target: TargetItem }[] }>();
    for (const pub of dayPubs) {
      for (const t of pub.targets.items) {
        const entry = map.get(t.account_id) ?? { username: t.username, rows: [] };
        entry.rows.push({ pub, target: t });
        map.set(t.account_id, entry);
      }
    }
    return [...map.entries()].map(([account_id, v]) => ({ account_id, ...v }))
      .sort((a, b) => a.username.localeCompare(b.username));
  }, [byDay, selectedDay]);

  const grid = useMemo(() => monthGrid(month), [month]);
  const todayKey = dayKey(new Date());
  const monthLabel = month.toLocaleDateString("pt-BR", { month: "long", year: "numeric" });
  const selectedAccountEntry = dayAccounts.find((a) => a.account_id === selectedAccount) ?? null;

  const dayLabel = (k: string) => {
    const [y, m, d] = k.split("-").map(Number);
    return new Date(y, m - 1, d).toLocaleDateString("pt-BR", { weekday: "long", day: "2-digit", month: "long" });
  };

  return (
    <div className="space-y-4">
      <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-semibold tracking-[-0.045em] text-fg sm:text-3xl">Publicações</h2>
          <p className="mt-1 text-sm text-muted">Calendário de posts e stories agendados. Clique num dia para ver as contas e os agendamentos.</p>
        </div>
        <button type="button" onClick={() => setFormOpen(true)}
          className="inline-flex h-10 items-center gap-2 rounded-lg bg-brand px-4 text-sm font-semibold text-white">
          <Plus size={16} /> Agendar nova publicação
        </button>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        {/* Calendar */}
        <section className="glass-panel p-4 sm:p-5">
          <div className="flex items-center justify-between">
            <button type="button" aria-label="Mês anterior"
              onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))}
              className="grid h-8 w-8 place-items-center rounded-lg border border-line text-fg hover:border-brand">
              <ChevronLeft size={16} />
            </button>
            <span className="text-sm font-semibold capitalize text-fg">{monthLabel}</span>
            <button type="button" aria-label="Próximo mês"
              onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))}
              className="grid h-8 w-8 place-items-center rounded-lg border border-line text-fg hover:border-brand">
              <ChevronRight size={16} />
            </button>
          </div>

          <div className="mt-3 grid grid-cols-7 gap-1 text-center text-[11px] uppercase tracking-wide text-muted">
            {WEEKDAYS.map((w) => <span key={w}>{w}</span>)}
          </div>
          <div className="mt-1 grid grid-cols-7 gap-1">
            {grid.map((d) => {
              const k = dayKey(d);
              const inMonth = d.getMonth() === month.getMonth();
              const dayPubs = byDay.get(k) ?? [];
              const isSelected = k === selectedDay;
              return (
                <button key={k} type="button"
                  onClick={() => { setSelectedDay(k); setSelectedAccount(null); }}
                  className={`relative aspect-square rounded-lg border p-1 text-left text-xs transition ${
                    isSelected ? "border-brand bg-brand/10" : "border-line hover:border-brand/60"
                  } ${inMonth ? "text-fg" : "text-muted/50"}`}>
                  <span className={`inline-grid h-5 w-5 place-items-center rounded-full ${
                    k === todayKey ? "bg-brand font-semibold text-white" : ""}`}>{d.getDate()}</span>
                  {dayPubs.length > 0 && (
                    <span className="absolute bottom-1 left-1 right-1 flex items-center justify-center gap-0.5">
                      {dayPubs.slice(0, 4).map((p) => (
                        <span key={p.id} className={`h-1.5 w-1.5 rounded-full ${p.kind === "story" ? "bg-accent" : "bg-brand"}`} />
                      ))}
                      {dayPubs.length > 4 && <span className="text-[9px] text-muted">+</span>}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
          <div className="mt-3 flex items-center gap-4 text-[11px] text-muted">
            <span className="flex items-center gap-1"><span className="h-1.5 w-1.5 rounded-full bg-brand" /> post</span>
            <span className="flex items-center gap-1"><span className="h-1.5 w-1.5 rounded-full bg-accent" /> story</span>
          </div>
        </section>

        {/* Drill-down: day -> accounts -> publications */}
        <section className="glass-panel p-4 sm:p-5">
          {!selectedDay && <p className="text-sm text-muted">Selecione um dia no calendário.</p>}
          {selectedDay && (
            <>
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-sm font-semibold capitalize text-fg">{dayLabel(selectedDay)}</h3>
                {selectedAccount && (
                  <button type="button" onClick={() => setSelectedAccount(null)}
                    className="inline-flex items-center gap-1 text-xs text-accent hover:text-white">
                    <ChevronLeft size={13} /> contas
                  </button>
                )}
              </div>

              {list.isLoading && <p className="mt-3 text-sm text-muted">Carregando...</p>}

              {/* Accounts of the day */}
              {!selectedAccount && (
                <div className="mt-3 space-y-1.5">
                  {dayAccounts.length === 0 && !list.isLoading && (
                    <p className="text-sm text-muted">Nenhuma publicação agendada neste dia.</p>
                  )}
                  {dayAccounts.map((a) => (
                    <button key={a.account_id} type="button" onClick={() => setSelectedAccount(a.account_id)}
                      className="flex w-full items-center justify-between gap-2 rounded-lg border border-line bg-surface-inset px-3 py-2 text-left text-sm hover:border-brand">
                      <span className="font-medium text-fg">@{a.username}</span>
                      <span className="flex items-center gap-2 text-xs text-muted">
                        {a.rows.length} agendamento{a.rows.length > 1 ? "s" : ""}
                        <ChevronRight size={14} />
                      </span>
                    </button>
                  ))}
                </div>
              )}

              {/* Publications of the selected account that day */}
              {selectedAccountEntry && (
                <div className="mt-3 space-y-2">
                  <p className="text-xs font-medium text-muted">@{selectedAccountEntry.username}</p>
                  {selectedAccountEntry.rows
                    .sort((x, y) => x.pub.scheduled_for.localeCompare(y.pub.scheduled_for))
                    .map(({ pub, target }) => (
                      <div key={pub.id + target.account_id} className="rounded-lg border border-line bg-surface-inset px-3 py-2">
                        <div className="flex items-center justify-between gap-2">
                          <span className="flex items-center gap-1.5 text-sm font-medium text-fg">
                            {pub.kind === "story" ? <Clapperboard size={14} /> : <ImageIcon size={14} />}
                            {pub.kind === "story" ? "Story" : "Post"} ·{" "}
                            {new Date(pub.scheduled_for).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}
                          </span>
                          <span className="flex items-center gap-1.5 text-xs text-muted">
                            <span className={`h-2 w-2 rounded-full ${TARGET_DOT[target.status] ?? "bg-muted"}`} />
                            {TARGET_LABEL[target.status] ?? target.status}
                          </span>
                        </div>
                        {pub.caption && <p className="mt-1 line-clamp-2 text-xs text-muted">{pub.caption}</p>}
                        <div className="mt-1 flex items-center gap-3 text-[11px] text-muted">
                          {pub.automation_id && (
                            <span className="inline-flex items-center gap-1 text-accent"><MessageCircle size={12} /> automação ligada</span>
                          )}
                          {(target.status === "queued") && (pub.status === "scheduled" || pub.status === "publishing") && (
                            <button type="button" onClick={() => { if (confirm("Cancelar esta publicação agendada?")) cancel.mutate(pub.id); }}
                              className="inline-flex items-center gap-1 text-danger hover:underline">
                              <Trash2 size={12} /> cancelar publicação
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                </div>
              )}
            </>
          )}
        </section>
      </div>

      {formOpen && (
        <ScheduleForm
          defaultDay={selectedDay}
          onClose={() => setFormOpen(false)}
          onSaved={() => { setFormOpen(false); cache.invalidateQueries({ queryKey: ["publications"] }); }}
        />
      )}
    </div>
  );
}

function defaultWhen(day: string | null): string {
  const base = day ? new Date(`${day}T12:00`) : new Date(Date.now() + 60 * 60 * 1000);
  if (day && base.getTime() <= Date.now()) base.setTime(Date.now() + 60 * 60 * 1000);
  base.setSeconds(0, 0);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${base.getFullYear()}-${pad(base.getMonth() + 1)}-${pad(base.getDate())}T${pad(base.getHours())}:${pad(base.getMinutes())}`;
}

function ScheduleForm({ defaultDay, onClose, onSaved }: { defaultDay: string | null; onClose: () => void; onSaved: () => void }) {
  const cache = useQueryClient();
  const media = useQuery({ queryKey: ["instagram", "media"], queryFn: () => apiRequest<MediaList>("/api/media") });
  const accountsQuery = useQuery({ queryKey: ["instagram", "accounts"], queryFn: () => apiRequest<AccountsList>("/api/instagram/accounts") });
  const foldersQuery = useQuery({ queryKey: ["instagram", "folders"], queryFn: () => apiRequest<FoldersList>("/api/instagram/folders?include_accounts=false") });
  const automationsQuery = useQuery({ queryKey: ["instagram", "automations"], queryFn: () => apiRequest<AutomationsList>("/api/instagram/automations") });

  const accounts = accountsQuery.data?.accounts ?? [];
  const folders = foldersQuery.data?.folders ?? [];
  const images = media.data?.media.filter((m) => m.media_type === "image") ?? [];
  const automations = (automationsQuery.data?.automations ?? []).filter((a) => a.trigger_type === "comment");

  const [kind, setKind] = useState<"post" | "story">("post");
  const [mediaId, setMediaId] = useState<string | null>(null);
  const [thumbId, setThumbId] = useState<string | null>(null);
  const [caption, setCaption] = useState("");
  const [when, setWhen] = useState(() => defaultWhen(defaultDay));
  const [accountIds, setAccountIds] = useState<string[]>([]);
  const [folderIds, setFolderIds] = useState<string[]>([]);
  const [automationId, setAutomationId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const selectedMedia = media.data?.media.find((m) => m.id === mediaId) ?? null;
  const isVideo = selectedMedia?.media_type === "video";

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const type = file.type === "video/mp4" ? "video/mp4" : "image/jpeg";
      return apiRequest<Media>(`/api/media?filename=${encodeURIComponent(file.name)}&purpose=post`, {
        method: "POST", headers: { "Content-Type": type }, body: file,
      });
    },
    onSuccess: (m) => { cache.invalidateQueries({ queryKey: ["instagram", "media"] }); setMediaId(m.id); setError(null); },
    onError: (e: unknown) => setError(e instanceof Error ? e.message : "Falha ao enviar a mídia."),
  });

  const toggle = (arr: string[], id: string) => (arr.includes(id) ? arr.filter((x) => x !== id) : [...arr, id]);
  const reach = useMemo(() => {
    const direct = new Set(accountIds);
    accounts.forEach((a) => { if (a.profile_folder_id && folderIds.includes(a.profile_folder_id)) direct.add(a.id); });
    return direct.size;
  }, [accountIds, folderIds, accounts]);

  const create = useMutation({
    mutationFn: () => {
      if (!mediaId) throw new Error("Escolha uma mídia.");
      if (accountIds.length === 0 && folderIds.length === 0) throw new Error("Escolha pelo menos uma conta ou pasta.");
      if (new Date(when).getTime() <= Date.now()) throw new Error("A data precisa ser no futuro.");
      return apiRequest<Publication>("/api/publications", {
        method: "POST",
        body: {
          media_id: mediaId,
          thumbnail_media_id: kind === "post" && isVideo ? thumbId : null,
          automation_id: kind === "post" ? automationId : null,
          kind,
          caption: kind === "post" ? caption : null,
          scheduled_for: new Date(when).toISOString(),
          account_ids: accountIds,
          folder_ids: folderIds,
        },
      });
    },
    onSuccess: onSaved,
    onError: (e: unknown) => setError(e instanceof Error ? e.message : "Não foi possível agendar."),
  });

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4" onClick={onClose}>
      <section className="glass-panel max-h-[90vh] w-full max-w-2xl space-y-4 overflow-y-auto p-4 sm:p-5" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h3 className="text-base font-semibold text-fg">Agendar nova publicação</h3>
          <button type="button" onClick={onClose} className="grid h-8 w-8 place-items-center rounded-lg border border-line text-muted hover:text-fg" aria-label="Fechar">
            <X size={15} />
          </button>
        </div>

        <div className="inline-flex rounded-lg border border-line p-0.5">
          {(["post", "story"] as const).map((k) => (
            <button key={k} type="button" onClick={() => setKind(k)}
              className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium ${kind === k ? "bg-brand text-white" : "text-muted hover:text-fg"}`}>
              {k === "post" ? <ImageIcon size={15} /> : <Clapperboard size={15} />} {k === "post" ? "Post no feed" : "Story"}
            </button>
          ))}
        </div>

        {/* Media */}
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
          <div className="grid grid-cols-4 gap-2 sm:grid-cols-6">
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

        {/* Thumbnail — feed video only */}
        {kind === "post" && isVideo && (
          <div>
            <span className="text-xs font-medium text-muted">Miniatura / capa (opcional — uma imagem)</span>
            <div className="mt-1 grid grid-cols-5 gap-2 sm:grid-cols-8">
              <button type="button" onClick={() => setThumbId(null)}
                className={`grid aspect-square place-items-center rounded-lg border text-[10px] ${thumbId === null ? "border-brand ring-2 ring-brand text-fg" : "border-line text-muted"}`}>
                padrão
              </button>
              {images.map((m) => (
                <button key={m.id} type="button" onClick={() => setThumbId(m.id)}
                  className={`relative aspect-square overflow-hidden rounded-lg border ${thumbId === m.id ? "border-brand ring-2 ring-brand" : "border-line"}`}>
                  <img src={`/api/media/${m.id}/preview`} alt={m.filename} className="h-full w-full object-cover" loading="lazy" />
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Caption */}
        {kind === "post" && (
          <label className="block text-xs font-medium text-muted">
            Legenda (opcional)
            <textarea className="mt-1 block w-full rounded-lg border border-line bg-surface-inset px-3 py-2 text-sm text-fg outline-none focus:border-brand"
              rows={2} maxLength={2200} value={caption} onChange={(e) => setCaption(e.target.value)} placeholder="Escreva a legenda do post..." />
          </label>
        )}

        {/* ManyChat automation — feed post only */}
        {kind === "post" && (
          <label className="block text-xs font-medium text-muted">
            Automação ManyChat (opcional — responde os comentários deste post)
            <select className="mt-1 block h-10 w-full rounded-lg border border-line bg-surface-inset px-3 text-sm text-fg outline-none focus:border-brand"
              value={automationId ?? ""} onChange={(e) => setAutomationId(e.target.value || null)}>
              <option value="">Nenhuma</option>
              {automations.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
            {automations.length === 0 && (
              <span className="mt-1 block text-[11px] text-muted">Crie uma automação de comentário em Contas → Automações para ligar aqui.</span>
            )}
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
            <div className="mt-1 max-h-40 space-y-1 overflow-y-auto rounded-lg border border-line p-2">
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
            <div className="mt-1 max-h-40 space-y-1 overflow-y-auto rounded-lg border border-line p-2">
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
          <div className="flex items-center gap-2">
            <button type="button" onClick={onClose} className="h-10 rounded-lg border border-line px-4 text-sm font-medium text-fg">Cancelar</button>
            <button type="button" disabled={create.isPending || !mediaId} onClick={() => create.mutate()}
              className="inline-flex h-10 items-center gap-2 rounded-lg bg-brand px-5 text-sm font-semibold text-white disabled:opacity-60">
              {create.isPending ? <LoaderCircle size={15} className="animate-spin" /> : <CalendarClock size={16} />} Agendar
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}

export default PublicationsPage;
