import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronRight, CopyPlus, Folder, Infinity as InfinityIcon, KeyRound, Lock, RotateCcw, Share2, SlidersHorizontal } from "lucide-react";

import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { CopyField } from "@/components/ui/CopyField";
import { Modal } from "@/components/ui/Modal";
import type { InstagramFoldersResponse, InstagramLoop, InstagramLoopAccountsPage } from "@/pages/loops/loopShared";
import { ApiError, apiRequest } from "@/services/api";
import { type PartnerOption, useChiefLabel, useMyPartners, useShareToggle, useSharedTemplates, useUseTemplate } from "./api";

const errorText = (error: unknown) => (error instanceof ApiError ? error.message : "Não foi possível concluir a ação.");

function AcceptFirst() {
  const chief = useChiefLabel();
  return (
    <p className="rounded-xl border border-warning/40 bg-warning-soft px-3 py-2 text-xs text-warning">
      Os modelos compartilhados por {chief} ficam disponíveis quando sua sociedade estiver ativa.
    </p>
  );
}

/** "Só seu", "Compartilhado com todos os sócios" or "Compartilhado com Ana, Bia". */
function shareLabel(item: { shared?: boolean; shared_with?: string[] | null }, partners: PartnerOption[]) {
  if (!item.shared) return "Só seu";
  if (!item.shared_with) return "Compartilhado com todos os sócios";
  const names = item.shared_with.map((id) => partners.find((partner) => partner.id === id)?.name.split(/\s+/)[0] ?? "sócio");
  return `Compartilhado com ${names.join(", ")}`;
}

type Shareable = { id: string; name: string; shared?: boolean; shared_with?: string[] | null; shared_loop_id?: string | null };

/** Chief: choose who receives a funnel or a loop (everyone or specific partners) and, for funnels, a loop to go with it. */
function ShareDialog({ item, kind, loops, onClose }: {
  item: Shareable | null;
  kind: "loops" | "flows";
  loops?: { id: string; name: string }[];
  onClose: () => void;
}) {
  const partners = useMyPartners(item !== null);
  const toggle = useShareToggle(kind);
  const [mode, setMode] = useState<"all" | "some">("all");
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [loopId, setLoopId] = useState("");

  useEffect(() => {
    if (!item) return;
    setMode(item.shared && item.shared_with ? "some" : "all");
    setPicked(new Set(item.shared && item.shared_with ? item.shared_with : []));
    setLoopId(item.shared ? item.shared_loop_id ?? "" : "");
    toggle.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item?.id]);

  if (!item) return null;
  const list = partners.data?.partners ?? [];
  const flip = (id: string) =>
    setPicked((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const share = () =>
    toggle.mutate(
      {
        id: item.id,
        shared: true,
        partner_ids: mode === "all" ? null : [...picked],
        loop_id: kind === "flows" ? loopId || null : null,
      },
      { onSuccess: onClose },
    );
  const stop = () => toggle.mutate({ id: item.id, shared: false }, { onSuccess: onClose });

  return (
    <Modal
      busy={toggle.isPending}
      description={
        kind === "flows"
          ? "O sócio roda o funil no bot dele sem ver nem copiar textos, mídias ou ofertas."
          : "O sócio recebe o loop pronto em “Loops compartilhados”: posta as mesmas mídias, mas só depois que ele conectar as contas dele."
      }
      footer={
        <div className="flex flex-wrap justify-end gap-2">
          {item.shared && (
            <Button disabled={toggle.isPending} onClick={stop} variant="danger">
              Parar de compartilhar
            </Button>
          )}
          <Button disabled={toggle.isPending || (mode === "some" && picked.size === 0)} onClick={share} variant="primary">
            <Share2 size={14} /> {item.shared ? "Salvar" : "Compartilhar"}
          </Button>
        </div>
      }
      onClose={onClose}
      open
      title={`Compartilhar “${item.name}”`}
    >
      <div className="space-y-4">
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium text-fg">Com quem</legend>
          <label className="flex items-center gap-2 text-sm text-fg-2">
            <input checked={mode === "all"} name="share-mode" onChange={() => setMode("all")} type="radio" />
            Todos os sócios (inclusive os que entrarem depois)
          </label>
          <label className="flex items-center gap-2 text-sm text-fg-2">
            <input checked={mode === "some"} name="share-mode" onChange={() => setMode("some")} type="radio" />
            Sócios específicos
          </label>
          {mode === "some" && (
            <div className="ml-6 space-y-1.5">
              {partners.isLoading && <LoadingState label="Carregando sócios" />}
              {partners.data && list.length === 0 && <p className="text-xs text-muted">Você ainda não tem sócios ativos.</p>}
              {list.map((partner) => (
                <label className="flex items-center gap-2 text-sm text-fg" key={partner.id}>
                  <input checked={picked.has(partner.id)} onChange={() => flip(partner.id)} type="checkbox" />
                  {partner.name}
                  {partner.nickname && <span className="text-xs text-muted">@{partner.nickname}</span>}
                </label>
              ))}
            </div>
          )}
        </fieldset>
        {kind === "flows" && (
          <label className="block space-y-1.5">
            <span className="text-sm font-medium text-fg">Compartilhar um loop junto (opcional)</span>
            <select className="field !min-h-10 text-sm" onChange={(event) => setLoopId(event.target.value)} value={loopId}>
              <option value="">Sem loop</option>
              {(loops ?? []).map((loop) => (
                <option key={loop.id} value={loop.id}>{loop.name}</option>
              ))}
            </select>
            <span className="block text-xs text-muted">
              O loop vai para os mesmos sócios e aparece pronto para eles, sem contas: começa a postar quando eles conectarem as
              contas deles.
            </span>
          </label>
        )}
        {toggle.error && <ErrorState message={errorText(toggle.error)} />}
      </div>
    </Modal>
  );
}

/** Chief: share a loop with every partner or with specific ones. */
export function ShareLoopButton({ loop }: { loop: InstagramLoop }) {
  const [open, setOpen] = useState(false);
  const [copiesOpen, setCopiesOpen] = useState(false);
  const partners = useMyPartners();
  if (loop.from_template || loop.linked) return null;
  const label = shareLabel(loop, partners.data?.partners ?? []);
  return (
    <>
      <button
        aria-label={`Compartilhar ${loop.name} com sócios`}
        aria-pressed={Boolean(loop.shared)}
        className={`grid size-9 place-items-center rounded-lg border hover:bg-surface-raised ${
          loop.shared ? "border-brand text-accent" : "border-line text-fg-2"
        }`}
        onClick={() => setOpen(true)}
        title={loop.shared ? `${label} (clique para mudar)` : "Compartilhar com sócios"}
        type="button"
      >
        <Share2 size={15} />
      </button>
      <ShareDialog item={open ? loop : null} kind="loops" onClose={() => setOpen(false)} />
      {loop.shared && (
        <>
          <button
            aria-label={`Ajustar o loop ${loop.name} de cada sócio`}
            className="grid size-9 place-items-center rounded-lg border border-line text-fg-2 hover:bg-surface-raised"
            onClick={() => setCopiesOpen(true)}
            title="Ajustar o loop de um sócio (sem mudar o seu)"
            type="button"
          >
            <SlidersHorizontal size={15} />
          </button>
          <PartnerCopiesDialog loop={copiesOpen ? loop : null} onClose={() => setCopiesOpen(false)} />
        </>
      )}
    </>
  );
}

type LoopCopy = {
  id: string;
  partner_name: string;
  customized: boolean;
  interval_min_minutes: number;
  interval_max_minutes: number;
  daily_limit_per_account: number;
  caption_mode: "per_media" | "all";
  caption: string | null;
  accounts_count: number;
  status: string;
};

/** Chief: each partner's copy of a shared loop. Changing one changes only that partner's
 *  loop (schedule, daily limit, caption); the main loop and the other partners stay as they are. */
function PartnerCopiesDialog({ loop, onClose }: { loop: InstagramLoop | null; onClose: () => void }) {
  const [editing, setEditing] = useState<string | null>(null);
  const copies = useQuery({
    queryKey: ["partners", "loop-copies", loop?.id],
    queryFn: () => apiRequest<{ copies: LoopCopy[] }>(`/api/partners/loops/${loop!.id}/copies`),
    enabled: loop !== null,
  });
  if (!loop) return null;
  const list = copies.data?.copies ?? [];
  return (
    <Modal
      description="Mude o loop de um sócio sem alterar o seu loop principal nem o dos outros sócios. As mídias continuam vindo do seu loop."
      onClose={() => {
        setEditing(null);
        onClose();
      }}
      open
      title={`Loop dos sócios - ${loop.name}`}
    >
      {copies.isLoading ? (
        <LoadingState label="Carregando os loops dos sócios" />
      ) : copies.error ? (
        <ErrorState message={errorText(copies.error)} onRetry={() => void copies.refetch()} />
      ) : list.length === 0 ? (
        <EmptyState message="Nenhum sócio abriu este loop ainda. Ele aparece aqui assim que o sócio entrar em Loops." />
      ) : (
        <div className="space-y-2">
          {list.map((copy) => (
            <div className="rounded-xl border border-line-soft bg-surface-inset p-3" key={copy.id}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-fg">{copy.partner_name}</p>
                  <p className="mt-0.5 text-[11px] text-muted">
                    a cada {copy.interval_min_minutes}–{copy.interval_max_minutes} min · até {copy.daily_limit_per_account}/dia por conta ·{" "}
                    {copy.accounts_count} conta(s)
                  </p>
                </div>
                {copy.customized ? <Badge tone="brand">Personalizado</Badge> : <Badge>Igual ao seu</Badge>}
              </div>
              {editing === copy.id ? (
                <CopyForm copy={copy} loopId={loop.id} onDone={() => setEditing(null)} />
              ) : (
                <Button className="mt-2" onClick={() => setEditing(copy.id)} size="sm">
                  <SlidersHorizontal size={14} /> Personalizar o loop deste sócio
                </Button>
              )}
            </div>
          ))}
        </div>
      )}
    </Modal>
  );
}

function CopyForm({ copy, loopId, onDone }: { copy: LoopCopy; loopId: string; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [min, setMin] = useState(String(copy.interval_min_minutes));
  const [max, setMax] = useState(String(copy.interval_max_minutes));
  const [limit, setLimit] = useState(String(copy.daily_limit_per_account));
  const [captionAll, setCaptionAll] = useState(copy.customized && copy.caption_mode === "all");
  const [caption, setCaption] = useState(copy.caption_mode === "all" ? copy.caption ?? "" : "");
  const url = `/api/partners/loops/${loopId}/copies/${copy.id}`;
  const done = () => {
    void queryClient.invalidateQueries({ queryKey: ["partners", "loop-copies", loopId] });
    onDone();
  };
  const save = useMutation({
    mutationFn: () =>
      apiRequest(url, {
        method: "PUT",
        body: {
          interval_min_minutes: Number(min),
          interval_max_minutes: Number(max),
          daily_limit_per_account: Number(limit),
          caption_mode: captionAll ? "all" : null,
          caption: captionAll ? caption : null,
        },
      }),
    onSuccess: done,
  });
  const reset = useMutation({ mutationFn: () => apiRequest(`${url}/customization`, { method: "DELETE" }), onSuccess: done });
  return (
    <div className="mt-3 space-y-3 border-t border-line-soft pt-3">
      <div className="grid grid-cols-3 gap-2">
        <label className="text-[11px] text-muted">
          Mínimo (min)
          <input className="field mt-1" inputMode="numeric" max={1440} min={1} onChange={(e) => setMin(e.target.value)} type="number" value={min} />
        </label>
        <label className="text-[11px] text-muted">
          Máximo (min)
          <input className="field mt-1" inputMode="numeric" max={1440} min={1} onChange={(e) => setMax(e.target.value)} type="number" value={max} />
        </label>
        <label className="text-[11px] text-muted">
          Posts/dia por conta
          <input className="field mt-1" inputMode="numeric" max={100} min={1} onChange={(e) => setLimit(e.target.value)} type="number" value={limit} />
        </label>
      </div>
      <label className="flex items-center gap-2 text-sm text-fg">
        <input checked={captionAll} onChange={(e) => setCaptionAll(e.target.checked)} type="checkbox" />
        Usar uma legenda só para este sócio em todos os posts
      </label>
      {captionAll && (
        <textarea className="field min-h-20" maxLength={2200} onChange={(e) => setCaption(e.target.value)} placeholder="Legenda dos posts deste sócio" value={caption} />
      )}
      {(save.error || reset.error) && <ErrorState message={errorText(save.error ?? reset.error)} />}
      <div className="flex flex-wrap gap-2">
        <Button disabled={save.isPending} onClick={() => save.mutate()} size="sm" variant="primary">
          Salvar só para {copy.partner_name.split(/\s+/)[0]}
        </Button>
        {copy.customized && (
          <Button disabled={reset.isPending} onClick={() => reset.mutate()} size="sm">
            <RotateCcw size={14} /> Voltar a seguir o seu loop
          </Button>
        )}
        <Button onClick={onDone} size="sm" variant="ghost">
          Cancelar
        </Button>
      </div>
    </div>
  );
}

/** Partner: the loops the chief shared, as "Loop - name". The partner doesn't open or edit
 *  the loop itself (media, schedule and limits are the chief's): a tap shows the accounts
 *  posting it and lets them pick accounts and account folders. */
export function SharedLoopsSection({ loops }: { loops: InstagramLoop[] }) {
  const chief = useChiefLabel();
  const queryClient = useQueryClient();
  const shared = useSharedTemplates();
  const [opened, setOpened] = useState<InstagramLoop | null>(null);
  const linked = loops.filter((loop) => loop.linked || loop.customized);
  const sharedCount = shared.data?.loops.length ?? 0;
  const availableCount = linked.filter((loop) => loop.linked_available).length;
  // Opening the area creates the partner's copies on the server; refresh the list once they exist.
  useEffect(() => {
    if (sharedCount > availableCount) void queryClient.invalidateQueries({ queryKey: ["loops"] });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shared.dataUpdatedAt]);
  if (shared.isLoading) return <LoadingState label="Carregando loops compartilhados" />;
  if (shared.error) {
    return <ErrorState message={errorText(shared.error)} onRetry={() => void shared.refetch()} />;
  }
  const data = shared.data!;
  if (!data.available || (linked.length === 0 && sharedCount === 0)) return null;
  return (
    <section className="glass-panel space-y-3 p-4">
      <div>
        <h3 className="flex items-center gap-2 text-base font-semibold text-fg">
          <InfinityIcon className="text-accent" size={17} /> Loops compartilhados por {chief}
        </h3>
        <p className="mt-1 text-xs text-muted">
          Toque no loop para ver as contas conectadas e escolher as contas ou pastas que postam nele.
        </p>
      </div>
      {!data.accepted && <AcceptFirst />}
      {linked.length === 0 ? (
        <LoadingState label="Preparando os loops compartilhados" />
      ) : (
        <div className="grid gap-2 sm:grid-cols-2">
          {linked.map((loop) => (
            <button
              className="flex items-center justify-between gap-3 rounded-xl border border-line-soft bg-surface-inset p-3 text-left transition-colors hover:border-line disabled:cursor-not-allowed disabled:opacity-60"
              disabled={!data.accepted || !loop.linked_available}
              key={loop.id}
              onClick={() => setOpened(loop)}
              type="button"
            >
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium text-fg">Loop - {loop.name}</span>
                <span className="mt-0.5 block text-xs text-muted">
                  {!loop.linked_available
                    ? "Parou de ser compartilhado"
                    : loop.active_accounts_count === 0
                      ? "Nenhuma conta conectada"
                      : `${loop.active_accounts_count} conta(s) conectada(s)`}
                </span>
              </span>
              <ChevronRight className="shrink-0 text-muted" size={16} />
            </button>
          ))}
        </div>
      )}
      <LoopAccountsDialog loop={opened} onClose={() => setOpened(null)} />
    </section>
  );
}

/** Collaborator: the operation's loops as "Loop - name", read-only; a tap shows the accounts
 *  posting it and lets them pick accounts (schedule, media and captions stay the owner's). */
export function ConnectOnlyLoops({ loops }: { loops: InstagramLoop[] }) {
  const [opened, setOpened] = useState<InstagramLoop | null>(null);
  if (loops.length === 0) return <EmptyState message="Nenhum loop nesta operação ainda." />;
  return (
    <section className="space-y-3">
      <p className="text-xs text-muted">Toque no loop para ver as contas conectadas e escolher as contas que postam nele.</p>
      <div className="grid gap-2 sm:grid-cols-2">
        {loops.map((loop) => (
          <button
            className="flex items-center justify-between gap-3 rounded-xl border border-line-soft bg-surface-inset p-3 text-left transition-colors hover:border-line"
            key={loop.id}
            onClick={() => setOpened(loop)}
            type="button"
          >
            <span className="min-w-0">
              <span className="block truncate text-sm font-medium text-fg">Loop - {loop.name}</span>
              <span className="mt-0.5 block text-xs text-muted">
                {loop.active_accounts_count === 0 ? "Nenhuma conta conectada" : `${loop.active_accounts_count} conta(s) conectada(s)`}
              </span>
            </span>
            <ChevronRight className="shrink-0 text-muted" size={16} />
          </button>
        ))}
      </div>
      <LoopAccountsDialog loop={opened} onClose={() => setOpened(null)} withFolders={false} />
    </section>
  );
}

/** The accounts posting a loop, and which accounts (and, for partners, folders) post it. */
function LoopAccountsDialog({ loop, onClose, withFolders = true }: { loop: InstagramLoop | null; onClose: () => void; withFolders?: boolean }) {
  const queryClient = useQueryClient();
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [pickedFolders, setPickedFolders] = useState<Set<string>>(new Set());
  const [initializedLoopId, setInitializedLoopId] = useState<string | null>(null);
  const accounts = useQuery({
    queryKey: ["loops", "accounts", "shared", loop?.id],
    queryFn: () => {
      const params = new URLSearchParams({ loop_id: loop!.id, limit: "1000" });
      return apiRequest<InstagramLoopAccountsPage>(`/api/loops/accounts?${params}`);
    },
    enabled: loop !== null,
    retry: false,
  });
  const folders = useQuery({
    queryKey: ["instagram", "folders"],
    queryFn: () => apiRequest<InstagramFoldersResponse>("/api/instagram/folders?include_accounts=false"),
    enabled: loop !== null && withFolders,
  });
  useEffect(() => {
    if (!loop) {
      setInitializedLoopId(null);
      return;
    }
    if (accounts.data && initializedLoopId !== loop.id) {
      setPicked(new Set(accounts.data.selected_ids));
      setPickedFolders(new Set(loop.auto_folder_ids ?? []));
      setInitializedLoopId(loop.id);
    }
  }, [accounts.data, initializedLoopId, loop]);
  const save = useMutation({
    mutationFn: () =>
      apiRequest(`/api/loops/${loop!.id}/accounts`, {
        method: "PUT",
        body: withFolders ? { account_ids: [...picked], auto_folder_ids: [...pickedFolders] } : { account_ids: [...picked] },
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["loops"] });
      onClose();
    },
  });
  if (!loop) return null;
  const usable = accounts.data?.accounts ?? [];
  const connected = usable.filter((account) => accounts.data?.selected_ids.includes(account.id));
  const toggle = (set: (fn: (current: Set<string>) => Set<string>) => void, id: string) =>
    set((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  return (
    <Modal
      busy={save.isPending}
      footer={
        <Button disabled={save.isPending || accounts.isLoading || Boolean(accounts.error)} onClick={() => save.mutate()} variant="primary">
          Salvar
        </Button>
      }
      onClose={onClose}
      open
      title={`Loop - ${loop.name}`}
    >
      {accounts.isLoading ? (
        <LoadingState label="Carregando contas conectadas" />
      ) : accounts.error ? (
        <ErrorState message={errorText(accounts.error)} />
      ) : (
        <div className="space-y-4">
          <section>
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted">Contas conectadas ({connected.length})</h4>
            {connected.length === 0 ? (
              <p className="mt-1 text-sm text-muted">Nenhuma conta postando neste loop ainda.</p>
            ) : (
              <ul className="mt-2 flex flex-wrap gap-1.5">
                {connected.map((account) => (
                  <li className="rounded-full bg-surface-inset px-2.5 py-1 text-xs text-fg" key={account.id}>@{account.username}</li>
                ))}
              </ul>
            )}
          </section>
          {withFolders && <section>
            <h4 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted">
              <Folder size={13} /> Pastas de contas
            </h4>
            <p className="mt-1 text-[11px] text-muted">As contas das pastas marcadas postam neste loop, inclusive as que entrarem depois.</p>
            {(folders.data?.folders ?? []).length === 0 ? (
              <p className="mt-1 text-sm text-muted">
                Você ainda não tem pastas. <Link className="text-accent underline" to="/feature/accounts">Crie em Contas</Link>.
              </p>
            ) : (
              <div className="mt-2 space-y-1.5">
                {folders.data!.folders.map((folder) => (
                  <label className="flex items-center gap-2 text-sm text-fg" key={folder.id}>
                    <input checked={pickedFolders.has(folder.id)} onChange={() => toggle(setPickedFolders, folder.id)} type="checkbox" />
                    <Folder size={13} style={{ color: folder.color }} /> {folder.name}
                  </label>
                ))}
              </div>
            )}
          </section>}
          <section>
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted">Contas</h4>
            {usable.length === 0 ? (
              <p className="mt-1 text-sm text-muted">
                Você ainda não tem contas do Instagram conectadas.{" "}
                <Link className="text-accent underline" to="/feature/accounts">Conecte uma conta</Link> e volte aqui.
              </p>
            ) : (
              <div className="mt-2 space-y-1.5">
                {usable.map((account) => (
                  <label className="flex items-center gap-2 text-sm text-fg" key={account.id}>
                    <input checked={picked.has(account.id)} onChange={() => toggle(setPicked, account.id)} type="checkbox" />
                    @{account.username}
                  </label>
                ))}
              </div>
            )}
          </section>
          {save.error && <ErrorState message={errorText(save.error)} />}
        </div>
      )}
    </Modal>
  );
}

/** Flash > Compartilhados comigo: the funnels another owner shared with me, with the
 *  rules that owner set (read-only: gateway, my part, the owner's commission). */
export function SharedFlowsPanel() {
  const chief = useChiefLabel();
  const shared = useSharedTemplates();
  const use = useUseTemplate("flows");
  const [setupFlow, setSetupFlow] = useState<string | null>(null);
  if (shared.isLoading) return <LoadingState label="Carregando funis compartilhados" />;
  if (shared.error) return <ErrorState message={errorText(shared.error)} onRetry={() => void shared.refetch()} />;
  const data = shared.data!;

  if (!data.available) {
    return (
      <div className="dashboard-card space-y-3 p-5">
        <EmptyState message="Nenhum funil foi compartilhado com você. Funis que você compartilha com seus sócios ficam em “Que compartilhei”." />
        <div className="flex justify-center">
          <Link className="btn-primary" to="/bot/compartilhei">
            <Share2 size={15} /> Ver o que compartilhei
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted">
        Funis de {chief} prontos para rodar no seu bot. As regras de divisão são definidas por {chief}. Funis pela SnakePay exigem que
        você configure a sua conta SnakePay (as vendas caem direto nela); funis pela SmokePay ou Athenas Pay usam as subcontas da
        plataforma e não exigem configuração. Quando o funil vem com um loop, ele aparece em Loops compartilhados, sem contas: conecte as
        suas e ele começa a postar. O conteúdo do
        funil é protegido; leads, vendas e métricas são seus.
      </p>
      {!data.accepted && <AcceptFirst />}
      {use.error && <ErrorState message={errorText(use.error)} />}
      {use.data && (
        <p className="text-xs text-success">
          Pronto! {use.data.loop ? `O loop “${use.data.loop.name}” está em Loops compartilhados (conecte suas contas nele). ` : ""}
          Agora vá em “Meus bots” e escolha “{use.data.name}” no seu bot, junto com o seu grupo de entrega.
        </p>
      )}
      {data.flows.length === 0 ? (
        <EmptyState message={`${chief} ainda não compartilhou nenhum funil com você.`} />
      ) : (
        <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
          {data.flows.map((flow) => (
            <Card className="space-y-3" key={flow.id}>
              <div className="flex items-start justify-between gap-2">
                <p className="min-w-0 truncate font-medium text-fg">{flow.name}</p>
                {flow.in_use && <Badge tone="success">No seu bot</Badge>}
              </div>
              <div className="flex items-center gap-2">
                <Badge>
                  {flow.rules.gateway === "snakepay" ? "SnakePay" : flow.rules.gateway === "atenaspay" ? "Athenas Pay" : "SmokePay"}
                </Badge>
                {flow.rules.needs_setup && <Badge tone="warning">Configure a SnakePay</Badge>}
              </div>
              <p className="text-xs text-muted">
                {flow.loop_name ? `Loop junto: ${flow.loop_name}${flow.loop_in_use ? " · já está nos seus loops" : ""}` : "Sem loop junto"}
              </p>
              {flow.rules.needs_setup ? (
                <>
                  <p className="flex items-start gap-1.5 text-[11px] leading-4 text-muted">
                    <Lock className="mt-0.5 shrink-0" size={12} />
                    Este funil cobra pela SnakePay. Configure a sua conta SnakePay para usá-lo: as vendas caem direto na sua conta.
                  </p>
                  <Button disabled={!data.accepted} onClick={() => setSetupFlow(flow.name)} size="sm" variant="primary">
                    <KeyRound size={14} /> Configurar SnakePay
                  </Button>
                </>
              ) : (
                <Button disabled={!data.accepted || use.isPending} onClick={() => use.mutate(flow.id)} size="sm" variant="primary">
                  {flow.loop_in_use || !flow.loop_name ? <Check size={14} /> : <CopyPlus size={14} />}{" "}
                  {flow.loop_name ? (flow.loop_in_use ? "Usar funil" : "Usar funil + loop") : "Usar funil"}
                </Button>
              )}
            </Card>
          ))}
        </div>
      )}
      <SnakepaySetupModal flowName={setupFlow} onClose={() => setSetupFlow(null)} />
    </div>
  );
}

/** The seller configures their own SnakePay (key + webhook) so they can use a shared SnakePay
 *  funnel. They never see the owner's commission, ShopID or any split detail. */
function SnakepaySetupModal({ flowName, onClose }: { flowName: string | null; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [apiKey, setApiKey] = useState("");
  const [secret, setSecret] = useState("");
  const webhook = useQuery({
    queryKey: ["payment-gateways"],
    queryFn: () => apiRequest<{ snakepay_webhook_url: string }>("/api/payment-gateways"),
    enabled: flowName !== null,
  });
  const save = useMutation({
    mutationFn: () =>
      apiRequest("/api/payment-gateways/snakepay/credentials", {
        method: "PUT",
        body: { api_key: apiKey.trim(), webhook_secret: secret.trim() },
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["partners", "shared"] }),
        queryClient.invalidateQueries({ queryKey: ["payment-gateways"] }),
      ]);
      onClose();
    },
  });

  useEffect(() => {
    if (flowName !== null) {
      setApiKey("");
      setSecret("");
      save.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flowName]);

  return (
    <Modal
      busy={save.isPending}
      description="As vendas deste funil caem direto na sua conta SnakePay. Suas credenciais ficam criptografadas e nunca são mostradas de novo."
      footer={
        <div className="flex flex-wrap justify-end gap-2">
          <Button onClick={onClose}>Cancelar</Button>
          <Button disabled={!apiKey.trim() || !secret.trim() || save.isPending} onClick={() => save.mutate()} variant="primary">
            <KeyRound size={14} /> {save.isPending ? "Salvando…" : "Salvar e liberar"}
          </Button>
        </div>
      }
      onClose={onClose}
      open={flowName !== null}
      title="Configurar SnakePay"
    >
      <div className="space-y-3">
        {webhook.data && (
          <CopyField
            hint="Cadastre esta URL na área Desenvolvedor da sua conta SnakePay, junto com o segredo do webhook."
            label="URL do webhook"
            value={webhook.data.snakepay_webhook_url}
          />
        )}
        <label className="block space-y-1.5">
          <span className="text-xs font-medium text-fg-2">Chave secreta da API</span>
          <input
            autoComplete="new-password"
            className="field font-mono text-xs"
            onChange={(event) => setApiKey(event.target.value)}
            placeholder="Chave da sua conta SnakePay"
            type="password"
            value={apiKey}
          />
        </label>
        <label className="block space-y-1.5">
          <span className="text-xs font-medium text-fg-2">Segredo do webhook</span>
          <input
            autoComplete="new-password"
            className="field font-mono text-xs"
            onChange={(event) => setSecret(event.target.value)}
            placeholder="Segredo configurado na SnakePay"
            type="password"
            value={secret}
          />
        </label>
        {save.error && <ErrorState message={errorText(save.error)} />}
      </div>
    </Modal>
  );
}
