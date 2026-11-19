import { useQuery } from "@tanstack/react-query";
import { Mic, Send, Trash2, Type } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { apiRequest } from "@/services/api";
import { emptyDelivery, type Block, type BotGroup, type Delivery, type OrderBump } from "../types";
import { MediaGrid } from "./MediaGrid";
import { BASE_VARIABLES, RichTextEditor } from "./RichTextEditor";
import { Field, MoneyInput, Switch } from "./ui";

const AFTER_UNITS = [
  { value: 1, label: "segundos" },
  { value: 60, label: "minutos" },
  { value: 3600, label: "horas" },
];

/** Seconds stored (0 = instant), shown as seconds/minutes/hours, capped at 24 h. */
function SecondsDelay({ value, onChange }: { value: number; onChange: (seconds: number) => void }) {
  const unit = value > 0 && value % 3600 === 0 ? 3600 : value > 0 && value % 60 === 0 ? 60 : 1;
  const immediate = value === 0;
  const clamp = (seconds: number) => Math.min(86400, Math.max(1, seconds));
  return (
    <div className="flex flex-wrap items-center gap-2">
      <select
        aria-label="Quando enviar"
        className="field !w-auto"
        value={immediate ? "now" : "later"}
        onChange={(event) => onChange(event.target.value === "now" ? 0 : 30)}
      >
        <option value="now">Imediato</option>
        <option value="later">Depois de…</option>
      </select>
      {!immediate && (
        <>
          <input
            aria-label="Tempo de espera"
            className="field !w-24"
            min={1}
            type="number"
            value={Math.max(1, Math.round(value / unit))}
            onChange={(event) => onChange(clamp((Number(event.target.value) || 1) * unit))}
          />
          <select
            aria-label="Unidade"
            className="field !w-auto"
            value={unit}
            onChange={(event) => onChange(clamp(Math.max(1, Math.round(value / unit)) * Number(event.target.value)))}
          >
            {AFTER_UNITS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </>
      )}
    </div>
  );
}

const newAfterText = (): Block => ({ type: "text", text: "", media_ids: [], spoiler: false, delay_seconds: 0 });
const newAfterAudio = (): Block => ({ type: "voice", text: null, media_ids: [], spoiler: false, delay_seconds: 0 });

/** Messages (text/audio) dripped to the buyer right after a delivery, for any purchase that
 *  uses it (plan, order bump, upsell or downsell). */
function AfterPurchase({ messages, onChange }: { messages: Block[]; onChange: (next: Block[]) => void }) {
  const setMsg = (index: number, patch: Partial<Block>) => onChange(messages.map((item, i) => (i === index ? { ...item, ...patch } : item)));
  return (
    <div className="space-y-2 border-t border-line-soft pt-4">
      <p className="flex items-center gap-2 text-sm font-medium text-fg">
        <Send size={15} className="text-accent" /> Mensagens após a compra <span className="text-xs text-muted">({messages.length}/10)</span>
      </p>
      <p className="text-xs leading-5 text-muted">
        Enviadas ao comprador logo depois desta entrega. Cada uma pode ser texto ou áudio, imediata ou com atraso.
      </p>
      {messages.map((message, index) => (
        <div className="grid gap-3 rounded-xl border border-line-soft p-3" key={index}>
          <div className="flex items-center justify-between gap-2">
            <span className="flex items-center gap-1.5 text-sm font-medium text-fg-2">
              {message.type === "voice" ? <Mic size={14} /> : <Type size={14} />}
              {message.type === "voice" ? "Áudio" : "Texto"} {index + 1}
            </span>
            <button aria-label="Remover mensagem" className="btn-ghost !min-h-9 !px-2 text-danger" onClick={() => onChange(messages.filter((_, i) => i !== index))} type="button">
              <Trash2 size={15} />
            </button>
          </div>
          {message.type === "voice" ? (
            <>
              <MediaGrid kinds={["audio"]} max={1} title="Áudio" value={message.media_ids} onChange={(media_ids) => setMsg(index, { media_ids })} />
              {message.media_ids.length === 0 && <p className="text-xs text-warning">Adicione o arquivo de áudio para esta mensagem.</p>}
            </>
          ) : (
            <RichTextEditor label="Mensagem" required rows={3} value={message.text ?? ""} variables={BASE_VARIABLES} onChange={(text) => setMsg(index, { text })} />
          )}
          <Field label={index === 0 ? "Enviar após a compra" : "Enviar depois da mensagem anterior"}>
            <SecondsDelay value={message.delay_seconds} onChange={(delay_seconds) => setMsg(index, { delay_seconds })} />
          </Field>
        </div>
      ))}
      {messages.length < 10 && (
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => onChange([...messages, newAfterText()])} size="sm" variant="secondary">
            <Type size={14} /> Texto
          </Button>
          <Button onClick={() => onChange([...messages, newAfterAudio()])} size="sm" variant="secondary">
            <Mic size={14} /> Áudio
          </Button>
        </div>
      )}
    </div>
  );
}

export function useBotGroups() {
  return useQuery({
    queryKey: ["bots", "groups"],
    queryFn: () => apiRequest<{ groups: BotGroup[] }>("/api/bots/groups/list"),
    retry: false,
  });
}

const types = [
  ["group", "Grupo/canal VIP"],
  ["pack", "Pack de mídias"],
  ["default", "Mensagem + link"],
  ["upsell", "Sequência de upsell"],
] as const;

export function DeliveryEditor({
  value,
  onChange,
  allowUpsell = true,
}: {
  value: Delivery;
  onChange: (next: Delivery) => void;
  /** Offers inside the upsell sequence cannot "deliver" the sequence again. */
  allowUpsell?: boolean;
}) {
  const groups = useBotGroups().data?.groups ?? [];
  const set = (patch: Partial<Delivery>) => onChange({ ...value, ...patch });
  const shownTypes = allowUpsell ? types : types.filter(([type]) => type !== "upsell");
  if (value.type === "upsell") {
    return (
      <div className="grid gap-3">
        <TypeTabs types={shownTypes} value={value.type} onPick={(type) => set({ type })} />
        <p className="rounded-xl border border-line-soft bg-surface-inset p-3 text-sm leading-6 text-muted">
          Depois do pagamento o bot não entrega conteúdo: ele começa direto a <b className="text-fg">sequência de upsell</b> configurada na seção Upsell.
        </p>
      </div>
    );
  }
  return (
    <div className="grid gap-3">
      <TypeTabs types={shownTypes} value={value.type} onPick={(type) => set({ type })} />
      {allowUpsell && (
        <label className="flex items-center justify-between gap-3 rounded-xl border border-line-soft p-3 text-sm text-fg-2">
          <span>Iniciar a sequência de upsell depois desta entrega</span>
          <Switch checked={value.start_upsell} label="Iniciar upsell depois da entrega" onChange={(start_upsell) => set({ start_upsell })} />
        </label>
      )}
      {value.type === "group" && (
        <>
          <Field
            label="Grupo ou canal"
            hint="Aparecem os grupos onde um bot seu é administrador com permissão de convidar. O comprador recebe um convite de uso único e sai sozinho quando o plano vence."
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
      {value.type !== "group" && (
        <MediaGrid
          max={50}
          title={value.type === "pack" ? "Mídias do pack (protegidas contra encaminhar/salvar)" : "Mídias (opcional)"}
          value={value.media_ids}
          onChange={(media_ids) => set({ media_ids })}
        />
      )}
      <RichTextEditor
        label="Mensagem da entrega"
        max={1000}
        rows={3}
        value={value.text ?? ""}
        variables={[...BASE_VARIABLES, "{plano}", "{valor}"]}
        onChange={(text) => set({ text })}
      />
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
      <AfterPurchase messages={value.after_purchase ?? []} onChange={(after_purchase) => set({ after_purchase })} />
    </div>
  );
}

function TypeTabs({
  types: shown,
  value,
  onPick,
}: {
  types: readonly (readonly [Delivery["type"], string])[];
  value: Delivery["type"];
  onPick: (type: Delivery["type"]) => void;
}) {
  return (
    <div className="inline-flex flex-wrap gap-1 rounded-2xl bg-well p-1" role="tablist" aria-label="Tipo de entrega">
      {shown.map(([type, label]) => (
        <button
          aria-selected={value === type}
          className={`min-h-9 rounded-full px-3 text-xs font-medium ${value === type ? "bg-brand text-white" : "text-muted"}`}
          key={type}
          onClick={() => onPick(type)}
          role="tab"
          type="button"
        >
          {label}
        </button>
      ))}
    </div>
  );
}

/** ``allowDefault``: the funnel editor offers "use the funnel's default delivery" (a
 * remarketing campaign has no funnel default, so its bump always brings its own). */
export function BumpEditor({
  value,
  onChange,
  allowDefault = false,
}: {
  value: OrderBump;
  onChange: (next: OrderBump) => void;
  allowDefault?: boolean;
}) {
  const set = (patch: Partial<OrderBump>) => onChange({ ...value, ...patch });
  return (
    <div className="grid gap-4">
      <div className="grid gap-3 sm:grid-cols-[1fr_160px]">
        <Field label="Nome do adicional">
          <input className="field" maxLength={60} value={value.name} onChange={(event) => set({ name: event.target.value })} />
        </Field>
        <MoneyInput label="Valor extra (R$)" value={value.price} onChange={(price) => set({ price })} />
      </div>
      <MediaGrid max={3} value={value.media_ids} onChange={(media_ids) => set({ media_ids })} />
      <RichTextEditor
        label="Pergunta"
        rows={3}
        value={value.text}
        variables={[...BASE_VARIABLES, "{bump}", "{bump_valor}", "{plano}", "{valor}"]}
        onChange={(text) => set({ text })}
        hint="Enviada antes do Pix. Se aceitar, o Pix sai com o total."
      />
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Botão de aceitar">
          <input className="field" maxLength={64} value={value.accept_label} onChange={(event) => set({ accept_label: event.target.value })} />
        </Field>
        <Field label="Botão de recusar">
          <input className="field" maxLength={64} value={value.decline_label} onChange={(event) => set({ decline_label: event.target.value })} />
        </Field>
      </div>
      <div className="space-y-2">
        <p className="text-sm font-medium text-fg">Entrega do adicional</p>
        {allowDefault && (
          <select
            className="field"
            value={value.delivery ? "own" : "default"}
            onChange={(event) => set({ delivery: event.target.value === "own" ? emptyDelivery("default") : null })}
          >
            <option value="default">Usar entrega padrão do funil</option>
            <option value="own">Entrega própria do adicional</option>
          </select>
        )}
        {value.delivery ? (
          <DeliveryEditor allowUpsell={false} value={value.delivery} onChange={(delivery) => set({ delivery })} />
        ) : allowDefault ? (
          <p className="text-xs text-muted">Quem comprar o adicional recebe a entrega padrão do funil (em Entrega padrão).</p>
        ) : (
          <button className="btn-secondary" onClick={() => set({ delivery: emptyDelivery("default") })} type="button">
            Definir a entrega do adicional
          </button>
        )}
      </div>
    </div>
  );
}
