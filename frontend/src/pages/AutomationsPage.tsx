import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  LoaderCircle,
  MessageCircle,
  Pencil,
  Plus,
  Trash2,
  X,
} from "lucide-react";

import { apiRequest } from "@/services/api";

type TriggerType = "comment" | "dm";
type MatchMode = "any" | "exact";
type LinkButton = { label: string; url: string };

type Automation = {
  id: string;
  name: string;
  enabled: boolean;
  trigger_type: TriggerType;
  instagram_account_id: string | null;
  keywords: string[];
  match_mode: MatchMode;
  media_id: string | null;
  public_reply_enabled: boolean;
  public_replies: string[];
  dm_enabled: boolean;
  dm_text: string | null;
  dm_buttons: LinkButton[];
  fired_count: number;
  last_fired_at: string | null;
};

type AutomationsResponse = { automations: Automation[]; live: boolean };
type AccountOption = { id: string; username: string; profile_picture_url: string | null };
type AccountsResponse = { accounts: AccountOption[] };

type Draft = {
  name: string;
  enabled: boolean;
  trigger_type: TriggerType;
  instagram_account_id: string | null;
  keywordsText: string;
  match_mode: MatchMode;
  public_reply_enabled: boolean;
  repliesText: string;
  dm_enabled: boolean;
  dm_text: string;
  dm_buttons: LinkButton[];
};

const INPUT =
  "mt-1 block h-10 w-full rounded-lg border border-line bg-surface-inset px-3 text-sm text-fg outline-none focus:border-brand";
const AREA =
  "mt-1 block w-full rounded-lg border border-line bg-surface-inset px-3 py-2 text-sm text-fg outline-none focus:border-brand";

function emptyDraft(): Draft {
  return {
    name: "",
    enabled: true,
    trigger_type: "comment",
    instagram_account_id: null,
    keywordsText: "",
    match_mode: "any",
    public_reply_enabled: true,
    repliesText: "",
    dm_enabled: true,
    dm_text: "",
    dm_buttons: [],
  };
}

function toDraft(rule: Automation): Draft {
  return {
    name: rule.name,
    enabled: rule.enabled,
    trigger_type: rule.trigger_type,
    instagram_account_id: rule.instagram_account_id,
    keywordsText: (rule.keywords ?? []).join(", "),
    match_mode: rule.match_mode,
    public_reply_enabled: rule.public_reply_enabled,
    repliesText: (rule.public_replies ?? []).join("\n"),
    dm_enabled: rule.dm_enabled,
    dm_text: rule.dm_text ?? "",
    dm_buttons: rule.dm_buttons ?? [],
  };
}

function toPayload(draft: Draft) {
  const keywords = draft.keywordsText
    .split(/[,\n]/)
    .map((kw) => kw.trim())
    .filter(Boolean)
    .slice(0, 30);
  const public_replies = draft.repliesText
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .slice(0, 10);
  return {
    name: draft.name.trim(),
    enabled: draft.enabled,
    trigger_type: draft.trigger_type,
    instagram_account_id: draft.instagram_account_id,
    keywords,
    match_mode: draft.match_mode,
    public_reply_enabled: draft.trigger_type === "comment" && draft.public_reply_enabled,
    public_replies,
    dm_enabled: draft.dm_enabled,
    dm_text: draft.dm_text.trim() || null,
    dm_buttons: draft.dm_buttons
      .map((b) => ({ label: b.label.trim(), url: b.url.trim() }))
      .filter((b) => b.label && b.url)
      .slice(0, 3),
  };
}

/** ManyChat-style Instagram automations: a keyword in a comment/DM fires a public
 * reply and/or a DM. The engine only sends for real once Meta approves the scopes;
 * until then rules are saved and matched, but sends are simulated (see the banner). */
export function AutomationsPage() {
  const cache = useQueryClient();
  const list = useQuery({
    queryKey: ["instagram", "automations"],
    queryFn: () => apiRequest<AutomationsResponse>("/api/instagram/automations"),
  });
  const accountsQuery = useQuery({
    queryKey: ["instagram", "accounts"],
    queryFn: () => apiRequest<AccountsResponse>("/api/instagram/accounts"),
  });
  const accounts = accountsQuery.data?.accounts ?? [];

  const [editing, setEditing] = useState<Automation | null>(null);
  const [creating, setCreating] = useState(false);

  const live = list.data?.live ?? false;
  const rules = list.data?.automations ?? [];

  const toggle = useMutation({
    mutationFn: (rule: Automation) =>
      apiRequest(`/api/instagram/automations/${rule.id}`, {
        method: "PUT",
        body: { ...toPayload(toDraft(rule)), enabled: !rule.enabled },
      }),
    onSuccess: () => cache.invalidateQueries({ queryKey: ["instagram", "automations"] }),
  });
  const remove = useMutation({
    mutationFn: (id: string) =>
      apiRequest(`/api/instagram/automations/${id}`, { method: "DELETE" }),
    onSuccess: () => cache.invalidateQueries({ queryKey: ["instagram", "automations"] }),
  });

  const accountName = (id: string | null) =>
    id ? accounts.find((a) => a.id === id)?.username ?? "conta" : "todas as contas";

  return (
    <div className="space-y-4">
      <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-semibold tracking-[-0.045em] text-fg sm:text-3xl">
            Automações
          </h2>
          <p className="mt-1 text-sm text-muted">
            Palavra-chave em comentário ou DM dispara uma resposta pública e uma mensagem no Direct.
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            setEditing(null);
            setCreating(true);
          }}
          className="inline-flex h-10 items-center gap-2 rounded-lg bg-brand px-4 text-sm font-semibold text-white"
        >
          <Plus size={16} /> Nova automação
        </button>
      </div>

      {!live && (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
          <strong>Modo simulação.</strong> As regras já ficam salvas e o sistema reconhece a
          palavra-chave, mas nada é enviado ao Instagram até a Meta aprovar as permissões de
          mensagens e comentários no App Review. Cada disparo fica registrado como “simulado”.
        </div>
      )}

      {(creating || editing) && (
        <AutomationForm
          key={editing?.id ?? "new"}
          initial={editing ? toDraft(editing) : emptyDraft()}
          accounts={accounts}
          onClose={() => {
            setCreating(false);
            setEditing(null);
          }}
          onSaved={() => {
            setCreating(false);
            setEditing(null);
            cache.invalidateQueries({ queryKey: ["instagram", "automations"] });
          }}
          ruleId={editing?.id ?? null}
        />
      )}

      <div className="space-y-2">
        {list.isLoading && <p className="text-sm text-muted">Carregando...</p>}
        {!list.isLoading && rules.length === 0 && (
          <div className="glass-panel grid place-items-center gap-2 p-10 text-center">
            <MessageCircle size={28} className="text-muted" />
            <p className="text-sm text-muted">
              Nenhuma automação ainda. Crie a primeira: escolha a palavra-chave e o que responder.
            </p>
          </div>
        )}
        {rules.map((rule) => (
          <article key={rule.id} className="glass-panel p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="truncate text-base font-semibold text-fg">{rule.name}</span>
                  <span
                    className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
                      rule.enabled ? "bg-success/15 text-success" : "bg-line text-muted"
                    }`}
                  >
                    {rule.enabled ? "ativa" : "pausada"}
                  </span>
                </div>
                <p className="mt-1 text-xs text-muted">
                  {rule.trigger_type === "comment" ? "Comentário" : "Direct"} ·{" "}
                  {accountName(rule.instagram_account_id)} ·{" "}
                  {rule.match_mode === "exact" ? "texto exato" : "contém a palavra"} · disparou{" "}
                  {rule.fired_count}×
                </p>
                <div className="mt-2 flex flex-wrap gap-1">
                  {rule.keywords.map((kw) => (
                    <span
                      key={kw}
                      className="rounded-md bg-surface-inset px-2 py-0.5 text-xs text-fg"
                    >
                      {kw}
                    </span>
                  ))}
                  {rule.keywords.length === 0 && (
                    <span className="text-xs text-amber-300">sem palavra-chave — não dispara</span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => toggle.mutate(rule)}
                  disabled={toggle.isPending}
                  className="rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-fg hover:border-brand"
                >
                  {rule.enabled ? "Pausar" : "Ativar"}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setCreating(false);
                    setEditing(rule);
                  }}
                  className="grid h-8 w-8 place-items-center rounded-lg border border-line text-fg hover:border-brand"
                  aria-label="Editar"
                >
                  <Pencil size={14} />
                </button>
                <button
                  type="button"
                  onClick={() => {
                    if (confirm(`Excluir a automação "${rule.name}"?`)) remove.mutate(rule.id);
                  }}
                  className="grid h-8 w-8 place-items-center rounded-lg border border-line text-danger hover:border-danger"
                  aria-label="Excluir"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

function AutomationForm({
  initial,
  accounts,
  ruleId,
  onClose,
  onSaved,
}: {
  initial: Draft;
  accounts: AccountOption[];
  ruleId: string | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [draft, setDraft] = useState<Draft>(initial);
  const [error, setError] = useState<string | null>(null);
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setDraft((d) => ({ ...d, [key]: value }));

  useEffect(() => setError(null), [draft]);

  const save = useMutation({
    mutationFn: () => {
      const payload = toPayload(draft);
      if (!payload.name) throw new Error("Dê um nome para a automação.");
      if (payload.keywords.length === 0) throw new Error("Adicione pelo menos uma palavra-chave.");
      if (!payload.public_reply_enabled && !payload.dm_enabled)
        throw new Error("Ative a resposta pública ou o Direct (ou os dois).");
      if (payload.dm_enabled && !payload.dm_text)
        throw new Error("Escreva a mensagem do Direct ou desative o Direct.");
      return apiRequest(
        ruleId ? `/api/instagram/automations/${ruleId}` : "/api/instagram/automations",
        { method: ruleId ? "PUT" : "POST", body: payload },
      );
    },
    onSuccess: onSaved,
    onError: (e: unknown) => setError(e instanceof Error ? e.message : "Não foi possível salvar."),
  });

  const isComment = draft.trigger_type === "comment";

  return (
    <section className="glass-panel space-y-4 p-4 sm:p-5">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold text-fg">
          {ruleId ? "Editar automação" : "Nova automação"}
        </h3>
        <button
          type="button"
          onClick={onClose}
          className="grid h-8 w-8 place-items-center rounded-lg border border-line text-muted hover:text-fg"
          aria-label="Fechar"
        >
          <X size={15} />
        </button>
      </div>

      <label className="block text-xs font-medium text-muted">
        Nome
        <input
          className={INPUT}
          value={draft.name}
          maxLength={120}
          placeholder="ex.: Link do grupo VIP"
          onChange={(e) => set("name", e.target.value)}
        />
      </label>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block text-xs font-medium text-muted">
          Gatilho
          <select
            className={INPUT}
            value={draft.trigger_type}
            onChange={(e) => set("trigger_type", e.target.value as TriggerType)}
          >
            <option value="comment">Comentário no post</option>
            <option value="dm">Mensagem no Direct</option>
          </select>
        </label>
        <label className="block text-xs font-medium text-muted">
          Conta
          <select
            className={INPUT}
            value={draft.instagram_account_id ?? ""}
            onChange={(e) => set("instagram_account_id", e.target.value || null)}
          >
            <option value="">Todas as contas</option>
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                @{a.username}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block text-xs font-medium text-muted">
          Palavras-chave (separe por vírgula)
          <input
            className={INPUT}
            value={draft.keywordsText}
            placeholder="quero, link, eu quero"
            onChange={(e) => set("keywordsText", e.target.value)}
          />
        </label>
        <label className="block text-xs font-medium text-muted">
          Como comparar
          <select
            className={INPUT}
            value={draft.match_mode}
            onChange={(e) => set("match_mode", e.target.value as MatchMode)}
          >
            <option value="any">Comentário contém a palavra</option>
            <option value="exact">Texto exato</option>
          </select>
        </label>
      </div>

      {isComment && (
        <div className="rounded-lg border border-line bg-surface-inset/40 p-3">
          <label className="flex items-center gap-2 text-sm font-medium text-fg">
            <input
              type="checkbox"
              checked={draft.public_reply_enabled}
              onChange={(e) => set("public_reply_enabled", e.target.checked)}
            />
            Responder o comentário publicamente
          </label>
          {draft.public_reply_enabled && (
            <label className="mt-2 block text-xs text-muted">
              Respostas (uma por linha — escolhe uma de cada vez, em rodízio)
              <textarea
                className={AREA}
                rows={3}
                value={draft.repliesText}
                placeholder={"Te chamei no Direct! 💬\nPronto, te mandei no privado 📩"}
                onChange={(e) => set("repliesText", e.target.value)}
              />
            </label>
          )}
        </div>
      )}

      <div className="rounded-lg border border-line bg-surface-inset/40 p-3">
        <label className="flex items-center gap-2 text-sm font-medium text-fg">
          <input
            type="checkbox"
            checked={draft.dm_enabled}
            onChange={(e) => set("dm_enabled", e.target.checked)}
          />
          Enviar mensagem no Direct
        </label>
        {draft.dm_enabled && (
          <>
            <label className="mt-2 block text-xs text-muted">
              Mensagem
              <textarea
                className={AREA}
                rows={3}
                maxLength={1000}
                value={draft.dm_text}
                placeholder="Oi! Aqui está o link que você pediu 👇"
                onChange={(e) => set("dm_text", e.target.value)}
              />
            </label>
            <ButtonsEditor
              buttons={draft.dm_buttons}
              onChange={(buttons) => set("dm_buttons", buttons)}
            />
          </>
        )}
      </div>

      {error && <p className="text-sm text-danger">{error}</p>}

      <div className="flex items-center justify-end gap-2">
        <button
          type="button"
          onClick={onClose}
          className="h-10 rounded-lg border border-line px-4 text-sm font-medium text-fg"
        >
          Cancelar
        </button>
        <button
          type="button"
          disabled={save.isPending}
          onClick={() => save.mutate()}
          className="inline-flex h-10 items-center gap-2 rounded-lg bg-brand px-5 text-sm font-semibold text-white disabled:opacity-60"
        >
          {save.isPending && <LoaderCircle size={15} className="animate-spin" />}
          {ruleId ? "Salvar" : "Criar automação"}
        </button>
      </div>
    </section>
  );
}

function ButtonsEditor({
  buttons,
  onChange,
}: {
  buttons: LinkButton[];
  onChange: (buttons: LinkButton[]) => void;
}) {
  const update = (i: number, patch: Partial<LinkButton>) =>
    onChange(buttons.map((b, idx) => (idx === i ? { ...b, ...patch } : b)));
  return (
    <div className="mt-3">
      <span className="text-xs text-muted">Botões com link (até 3)</span>
      <div className="mt-1 space-y-2">
        {buttons.map((b, i) => (
          <div key={i} className="flex items-center gap-2">
            <input
              className="h-9 w-1/3 rounded-lg border border-line bg-surface-inset px-2 text-sm text-fg outline-none focus:border-brand"
              value={b.label}
              maxLength={40}
              placeholder="Texto"
              onChange={(e) => update(i, { label: e.target.value })}
            />
            <input
              className="h-9 flex-1 rounded-lg border border-line bg-surface-inset px-2 text-sm text-fg outline-none focus:border-brand"
              value={b.url}
              placeholder="https://..."
              onChange={(e) => update(i, { url: e.target.value })}
            />
            <button
              type="button"
              onClick={() => onChange(buttons.filter((_, idx) => idx !== i))}
              className="grid h-9 w-9 place-items-center rounded-lg border border-line text-muted hover:text-danger"
              aria-label="Remover botão"
            >
              <X size={14} />
            </button>
          </div>
        ))}
      </div>
      {buttons.length < 3 && (
        <button
          type="button"
          onClick={() => onChange([...buttons, { label: "", url: "" }])}
          className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-accent hover:text-white"
        >
          <Plus size={13} /> Adicionar botão
        </button>
      )}
    </div>
  );
}

export default AutomationsPage;
