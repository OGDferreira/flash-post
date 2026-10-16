import { useEffect, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowLeft, ArrowUp, Plus, Save, Trash2 } from "lucide-react";

import { ErrorState, LoadingState } from "@/components/PageState";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ApiError, apiRequest } from "@/services/api";
import { MediaPicker } from "./MediaPicker";
import {
  emptyDelivery,
  type Block,
  type BlockType,
  type BotGroup,
  type BotMedia,
  type Delivery,
  type Flow,
  type FlowDefinition,
  type Plan,
} from "./types";

const blockTypes: { value: BlockType; label: string; kinds: BotMedia["kind"][]; max: number }[] = [
  { value: "text", label: "Texto", kinds: [], max: 0 },
  { value: "photo", label: "Foto", kinds: ["photo"], max: 1 },
  { value: "video", label: "Vídeo", kinds: ["video"], max: 1 },
  { value: "voice", label: "Áudio de voz", kinds: ["audio"], max: 1 },
  { value: "video_note", label: "Vídeo redondo", kinds: ["video"], max: 1 },
  { value: "album", label: "Álbum (2 a 10)", kinds: ["photo", "video"], max: 10 },
];

const durations: { value: number | null; label: string }[] = [
  { value: 1, label: "1 dia" },
  { value: 7, label: "Semanal" },
  { value: 15, label: "Quinzenal" },
  { value: 30, label: "Mensal" },
  { value: 90, label: "Trimestral" },
  { value: 180, label: "Semestral" },
  { value: 365, label: "Anual" },
  { value: null, label: "Vitalício" },
];

const VARIABLES = "Variáveis: {nome} {username} {plano} {valor}";

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="grid gap-1.5 text-sm text-fg-2">
      {label}
      {children}
      {hint && <span className="text-xs text-muted">{hint}</span>}
    </label>
  );
}

function Section({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return (
    <Card className="space-y-4">
      <div>
        <h3 className="font-medium text-fg">{title}</h3>
        {description && <p className="mt-1 text-sm leading-6 text-muted">{description}</p>}
      </div>
      {children}
    </Card>
  );
}

function move<T>(list: T[], index: number, delta: number): T[] {
  const target = index + delta;
  if (target < 0 || target >= list.length) return list;
  const copy = [...list];
  [copy[index], copy[target]] = [copy[target], copy[index]];
  return copy;
}

const blank = (value?: string | null) => (value && value.trim() ? value : null);

function cleanDelivery(delivery: Delivery | null | undefined): Delivery | null {
  if (!delivery) return null;
  return {
    ...delivery,
    group_chat_id: delivery.type === "group" ? delivery.group_chat_id ?? null : null,
    text: blank(delivery.text),
    media_ids: delivery.type === "group" ? [] : delivery.media_ids,
    link: delivery.link && delivery.link.label.trim() && delivery.link.url.trim() ? delivery.link : null,
  };
}

/** Strips UI-only empties so the backend validator sees exactly what the user set. */
function toPayload(definition: FlowDefinition): FlowDefinition {
  return {
    ...definition,
    welcome: definition.welcome.map((block) => ({
      ...block,
      text: block.type === "voice" || block.type === "video_note" ? null : blank(block.text),
      media_ids: block.type === "text" ? [] : block.media_ids,
    })),
    offer: { ...definition.offer, media_id: definition.offer.media_id || null },
    plans: definition.plans.map((plan) => ({
      ...plan,
      price: Number(String(plan.price).replace(",", ".")).toFixed(2),
      button_text: blank(plan.button_text),
      delivery: cleanDelivery(plan.delivery),
    })),
    default_delivery: cleanDelivery(definition.default_delivery),
  };
}

function DeliveryEditor({ value, onChange, groups }: { value: Delivery; onChange: (next: Delivery) => void; groups: BotGroup[] }) {
  const set = (patch: Partial<Delivery>) => onChange({ ...value, ...patch });
  return (
    <div className="grid gap-3">
      <div className="inline-flex flex-wrap gap-1 rounded-full bg-well p-1" role="tablist" aria-label="Tipo de entrega">
        {(
          [
            ["group", "Grupo/canal VIP"],
            ["pack", "Pack de mídias"],
            ["default", "Mensagem + link"],
          ] as const
        ).map(([type, label]) => (
          <button
            aria-selected={value.type === type}
            className={`min-h-9 rounded-full px-3 text-xs font-medium ${value.type === type ? "bg-brand text-white" : "text-muted"}`}
            key={type}
            onClick={() => set({ type })}
            role="tab"
            type="button"
          >
            {label}
          </button>
        ))}
      </div>
      {value.type === "group" && (
        <>
          <Field
            label="Grupo ou canal"
            hint="Aparecem aqui os grupos onde algum robô seu é administrador. O comprador recebe um convite de uso único e sai sozinho quando o plano vence."
          >
            <select
              className="field"
              value={value.group_chat_id ?? ""}
              onChange={(event) => set({ group_chat_id: event.target.value ? Number(event.target.value) : null })}
            >
              <option value="">Escolha…</option>
              {groups.map((group) => (
                <option disabled={!group.can_invite} key={group.chat_id} value={group.chat_id}>
                  {group.title} (@{group.bot}){group.can_invite ? "" : " — sem permissão de convidar"}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Texto do botão de entrada">
            <input className="field" maxLength={64} value={value.join_button_label} onChange={(event) => set({ join_button_label: event.target.value })} />
          </Field>
        </>
      )}
      {value.type === "pack" && (
        <Field label="Mídias do pack" hint="Enviadas protegidas: o comprador não consegue encaminhar nem salvar.">
          <MediaPicker max={50} value={value.media_ids} onChange={(media_ids) => set({ media_ids })} />
        </Field>
      )}
      <Field label="Mensagem da entrega" hint={VARIABLES}>
        <textarea className="field min-h-20" maxLength={1000} value={value.text ?? ""} onChange={(event) => set({ text: event.target.value })} />
      </Field>
      {value.type === "default" && (
        <Field label="Mídias (opcional)">
          <MediaPicker max={50} value={value.media_ids} onChange={(media_ids) => set({ media_ids })} />
        </Field>
      )}
      {value.type !== "group" && (
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Botão com link (opcional)">
            <input
              className="field"
              maxLength={64}
              placeholder="Ex.: Acessar conteúdo"
              value={value.link?.label ?? ""}
              onChange={(event) => set({ link: { label: event.target.value, url: value.link?.url ?? "" } })}
            />
          </Field>
          <Field label="URL do link">
            <input
              className="field"
              placeholder="https://"
              value={value.link?.url ?? ""}
              onChange={(event) => set({ link: { label: value.link?.label ?? "", url: event.target.value } })}
            />
          </Field>
        </div>
      )}
    </div>
  );
}

function BlockEditor({
  block,
  index,
  total,
  onChange,
  onMove,
  onRemove,
}: {
  block: Block;
  index: number;
  total: number;
  onChange: (next: Block) => void;
  onMove: (delta: number) => void;
  onRemove: () => void;
}) {
  const meta = blockTypes.find((item) => item.value === block.type)!;
  const hasCaption = block.type !== "voice" && block.type !== "video_note";
  return (
    <Card tone="inset" className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold text-accent">#{index + 1}</span>
        <select
          aria-label="Tipo do bloco"
          className="field !min-h-9 !w-auto !text-xs"
          value={block.type}
          onChange={(event) => onChange({ ...block, type: event.target.value as BlockType, media_ids: [] })}
        >
          {blockTypes.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-1.5 text-xs text-muted">
          Esperar
          <input
            className="field !min-h-9 !w-20 !text-xs"
            min={0}
            max={86400}
            type="number"
            value={block.delay_seconds}
            onChange={(event) => onChange({ ...block, delay_seconds: Math.max(0, Number(event.target.value) || 0) })}
          />
          s antes
        </label>
        <span className="ml-auto flex gap-1">
          <button aria-label="Subir" className="btn-ghost !min-h-8 !px-2" disabled={index === 0} onClick={() => onMove(-1)} type="button">
            <ArrowUp size={14} />
          </button>
          <button aria-label="Descer" className="btn-ghost !min-h-8 !px-2" disabled={index === total - 1} onClick={() => onMove(1)} type="button">
            <ArrowDown size={14} />
          </button>
          <button aria-label="Remover bloco" className="btn-ghost !min-h-8 !px-2 text-danger" onClick={onRemove} type="button">
            <Trash2 size={14} />
          </button>
        </span>
      </div>
      {meta.max > 0 && <MediaPicker kinds={meta.kinds} max={meta.max} value={block.media_ids} onChange={(media_ids) => onChange({ ...block, media_ids })} />}
      {hasCaption && (
        <textarea
          aria-label={block.type === "text" ? "Texto" : "Legenda"}
          className="field min-h-20"
          maxLength={1000}
          placeholder={block.type === "text" ? "Mensagem… use {nome} para o nome do lead" : "Legenda (opcional)"}
          value={block.text ?? ""}
          onChange={(event) => onChange({ ...block, text: event.target.value })}
        />
      )}
      {(block.type === "photo" || block.type === "video" || block.type === "album") && (
        <label className="flex items-center gap-2 text-xs text-muted">
          <input checked={block.spoiler} type="checkbox" onChange={(event) => onChange({ ...block, spoiler: event.target.checked })} />
          Borrar mídia (spoiler — o lead toca para ver)
        </label>
      )}
    </Card>
  );
}

function PlanEditor({
  plan,
  groups,
  onChange,
  onRemove,
}: {
  plan: Plan;
  groups: BotGroup[];
  onChange: (next: Plan) => void;
  onRemove: () => void;
}) {
  return (
    <Card tone="inset" className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-[1fr_140px_160px]">
        <Field label="Nome do plano">
          <input className="field" maxLength={60} value={plan.name} onChange={(event) => onChange({ ...plan, name: event.target.value })} />
        </Field>
        <Field label="Preço (R$)">
          <input
            className="field"
            inputMode="decimal"
            value={plan.price}
            onChange={(event) => onChange({ ...plan, price: event.target.value.replace(/[^\d.,]/g, "") })}
          />
        </Field>
        <Field label="Duração">
          <select
            className="field"
            value={plan.duration_days ?? "life"}
            onChange={(event) => onChange({ ...plan, duration_days: event.target.value === "life" ? null : Number(event.target.value) })}
          >
            {durations.map((item) => (
              <option key={item.label} value={item.value ?? "life"}>
                {item.label}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <Field label="Texto do botão (opcional)" hint="Vazio = “Nome · Preço”.">
        <input className="field" maxLength={64} value={plan.button_text ?? ""} onChange={(event) => onChange({ ...plan, button_text: event.target.value })} />
      </Field>
      <label className="flex items-center gap-2 text-sm text-fg-2">
        <input
          checked={!!plan.delivery}
          type="checkbox"
          onChange={(event) => onChange({ ...plan, delivery: event.target.checked ? emptyDelivery("group") : null })}
        />
        Entrega própria para este plano (senão usa a entrega padrão do fluxo)
      </label>
      {plan.delivery && <DeliveryEditor groups={groups} value={plan.delivery} onChange={(delivery) => onChange({ ...plan, delivery })} />}
      <div className="flex justify-end">
        <Button size="sm" variant="danger" onClick={onRemove}>
          <Trash2 size={14} /> Remover plano
        </Button>
      </div>
    </Card>
  );
}

export function FlowEditor({ flowId, onBack }: { flowId: string; onBack: () => void }) {
  const queryClient = useQueryClient();
  const flow = useQuery({ queryKey: ["bots", "flow", flowId], queryFn: () => apiRequest<Flow>(`/api/bots/flows/${flowId}`), retry: false });
  const groups = useQuery({
    queryKey: ["bots", "groups"],
    queryFn: () => apiRequest<{ groups: BotGroup[] }>("/api/bots/groups/list"),
    retry: false,
  });
  const [name, setName] = useState("");
  const [draft, setDraft] = useState<FlowDefinition | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (flow.data && !draft) {
      setName(flow.data.name);
      setDraft(flow.data.definition);
    }
  }, [flow.data, draft]);

  const save = useMutation({
    mutationFn: () => apiRequest<Flow>(`/api/bots/flows/${flowId}`, { method: "PUT", body: { name, definition: toPayload(draft!) } }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["bots", "flow", flowId], updated);
      void queryClient.invalidateQueries({ queryKey: ["bots", "flows"] });
      setDraft(updated.definition);
      setSaved(true);
      window.setTimeout(() => setSaved(false), 2500);
    },
  });

  if (flow.isLoading || (flow.data && !draft)) return <LoadingState label="Abrindo fluxo" />;
  if (flow.error || !draft) {
    return (
      <ErrorState
        message={flow.error instanceof ApiError ? flow.error.message : "Não foi possível abrir o fluxo."}
        onRetry={() => void flow.refetch()}
      />
    );
  }
  const set = (patch: Partial<FlowDefinition>) => setDraft({ ...draft, ...patch });
  const groupList = groups.data?.groups ?? [];
  const setBlock = (index: number, block: Block) => set({ welcome: draft.welcome.map((item, i) => (i === index ? block : item)) });
  const setPlan = (index: number, plan: Plan) => set({ plans: draft.plans.map((item, i) => (i === index ? plan : item)) });

  return (
    <div className="space-y-4 pb-24">
      <div className="flex flex-wrap items-center gap-3">
        <Button size="sm" variant="ghost" onClick={onBack}>
          <ArrowLeft size={15} /> Fluxos
        </Button>
        <input aria-label="Nome do fluxo" className="field min-w-0 flex-1 !text-base font-medium" maxLength={120} value={name} onChange={(event) => setName(event.target.value)} />
      </div>

      <Section title="Verificação +18" description="Antes de tudo, o lead confirma a idade num botão.">
        <label className="flex items-center gap-2 text-sm text-fg-2">
          <input
            checked={draft.age_gate.enabled}
            type="checkbox"
            onChange={(event) => set({ age_gate: { ...draft.age_gate, enabled: event.target.checked } })}
          />
          Ativar verificação de idade
        </label>
        {draft.age_gate.enabled && (
          <div className="grid gap-3">
            <Field label="Mensagem">
              <textarea className="field min-h-20" value={draft.age_gate.text} onChange={(event) => set({ age_gate: { ...draft.age_gate, text: event.target.value } })} />
            </Field>
            <Field label="Botão">
              <input className="field" maxLength={64} value={draft.age_gate.button} onChange={(event) => set({ age_gate: { ...draft.age_gate, button: event.target.value } })} />
            </Field>
          </div>
        )}
      </Section>

      <Section
        title="Boas-vindas"
        description="Sequência enviada no /start, na ordem, respeitando a espera de cada bloco. Use texto, foto, vídeo, áudio de voz, vídeo redondo ou álbum."
      >
        <div className="space-y-3">
          {draft.welcome.map((block, index) => (
            <BlockEditor
              block={block}
              index={index}
              key={index}
              total={draft.welcome.length}
              onChange={(next) => setBlock(index, next)}
              onMove={(delta) => set({ welcome: move(draft.welcome, index, delta) })}
              onRemove={() => set({ welcome: draft.welcome.filter((_, i) => i !== index) })}
            />
          ))}
        </div>
        <Button
          size="sm"
          disabled={draft.welcome.length >= 30}
          onClick={() => set({ welcome: [...draft.welcome, { type: "text", text: "", media_ids: [], spoiler: false, delay_seconds: 2 }] })}
        >
          <Plus size={14} /> Adicionar bloco
        </Button>
        <p className="text-xs text-muted">{VARIABLES}</p>
      </Section>

      <Section title="Oferta" description="Mensagem com os botões dos planos, enviada logo depois das boas-vindas.">
        <Field label="Texto da oferta" hint={VARIABLES}>
          <textarea className="field min-h-20" value={draft.offer.text} onChange={(event) => set({ offer: { ...draft.offer, text: event.target.value } })} />
        </Field>
        <Field label="Imagem ou vídeo da oferta (opcional)">
          <MediaPicker
            kinds={["photo", "video"]}
            max={1}
            value={draft.offer.media_id ? [draft.offer.media_id] : []}
            onChange={(ids) => set({ offer: { ...draft.offer, media_id: ids[0] ?? null } })}
          />
        </Field>
      </Section>

      <Section title="Planos" description="Cada plano vira um botão. O mínimo do Pix é R$ 1,00.">
        <div className="space-y-3">
          {draft.plans.map((plan, index) => (
            <PlanEditor
              groups={groupList}
              key={plan.id}
              plan={plan}
              onChange={(next) => setPlan(index, next)}
              onRemove={() => set({ plans: draft.plans.filter((_, i) => i !== index) })}
            />
          ))}
        </div>
        <Button
          size="sm"
          disabled={draft.plans.length >= 10}
          onClick={() =>
            set({
              plans: [
                ...draft.plans,
                { id: `p${Date.now().toString(36)}`, name: "Plano mensal", price: "29.90", duration_days: 30, button_text: null, delivery: null },
              ],
            })
          }
        >
          <Plus size={14} /> Adicionar plano
        </Button>
      </Section>

      <Section title="Entrega padrão" description="Usada pelos planos sem entrega própria.">
        <label className="flex items-center gap-2 text-sm text-fg-2">
          <input
            checked={!!draft.default_delivery}
            type="checkbox"
            onChange={(event) => set({ default_delivery: event.target.checked ? emptyDelivery("group") : null })}
          />
          Definir entrega padrão
        </label>
        {draft.default_delivery && (
          <DeliveryEditor groups={groupList} value={draft.default_delivery} onChange={(default_delivery) => set({ default_delivery })} />
        )}
      </Section>

      <Section title="Pagamento Pix" description="Textos do Pix e quanto tempo o código vale.">
        <Field label="Validade do Pix (minutos)">
          <input
            className="field !w-32"
            max={1440}
            min={5}
            type="number"
            value={draft.payment.expiration_minutes}
            onChange={(event) => set({ payment: { ...draft.payment, expiration_minutes: Number(event.target.value) || 30 } })}
          />
        </Field>
        {(
          [
            ["pix_text", "Mensagem do Pix", true],
            ["approved_text", "Pagamento aprovado", true],
            ["expired_text", "Pix expirado", true],
            ["pending_text", "Resposta ao “Já paguei” sem pagamento", false],
            ["copy_button", "Botão copiar", false],
            ["check_button", "Botão verificar", false],
          ] as const
        ).map(([key, label, multiline]) => (
          <Field hint={multiline ? VARIABLES : undefined} key={key} label={label}>
            {multiline ? (
              <textarea className="field min-h-20" value={draft.payment[key]} onChange={(event) => set({ payment: { ...draft.payment, [key]: event.target.value } })} />
            ) : (
              <input className="field" value={draft.payment[key]} onChange={(event) => set({ payment: { ...draft.payment, [key]: event.target.value } })} />
            )}
          </Field>
        ))}
      </Section>

      <div className="sticky bottom-[calc(env(safe-area-inset-bottom)+92px)] z-10 mr-14 flex lg:bottom-3 lg:mr-16 flex-wrap items-center justify-end gap-3 rounded-2xl border border-line bg-surface/95 p-3 backdrop-blur">
        {save.error && (
          <p className="mr-auto text-sm text-danger">{save.error instanceof ApiError ? save.error.message : "Não foi possível salvar."}</p>
        )}
        {saved && <p className="mr-auto text-sm text-success">Fluxo salvo. Vale para os próximos leads.</p>}
        <Button variant="primary" disabled={save.isPending || !name.trim()} onClick={() => save.mutate()}>
          <Save size={15} /> {save.isPending ? "Salvando..." : "Salvar fluxo"}
        </Button>
      </div>
    </div>
  );
}
