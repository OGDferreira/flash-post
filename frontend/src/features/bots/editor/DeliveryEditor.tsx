import { useQuery } from "@tanstack/react-query";

import { apiRequest } from "@/services/api";
import type { BotGroup, Delivery, OrderBump } from "../types";
import { MediaGrid } from "./MediaGrid";
import { BASE_VARIABLES, RichTextEditor } from "./RichTextEditor";
import { Field, MoneyInput } from "./ui";

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
] as const;

export function DeliveryEditor({ value, onChange }: { value: Delivery; onChange: (next: Delivery) => void }) {
  const groups = useBotGroups().data?.groups ?? [];
  const set = (patch: Partial<Delivery>) => onChange({ ...value, ...patch });
  return (
    <div className="grid gap-3">
      <div className="inline-flex flex-wrap gap-1 rounded-full bg-well p-1" role="tablist" aria-label="Tipo de entrega">
        {types.map(([type, label]) => (
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
            hint="Aparecem os grupos onde um robô seu é administrador com permissão de convidar. O comprador recebe um convite de uso único e sai sozinho quando o plano vence."
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
    </div>
  );
}

export function BumpEditor({ value, onChange }: { value: OrderBump; onChange: (next: OrderBump) => void }) {
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
        <DeliveryEditor value={value.delivery} onChange={(delivery) => set({ delivery })} />
      </div>
    </div>
  );
}
