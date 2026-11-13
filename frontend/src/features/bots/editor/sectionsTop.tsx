import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Bot as BotIcon, Crown, DollarSign, Globe, Languages, Link2, ListOrdered, MessageSquare, MousePointerClick, Plus, Trash2, Users } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { ConnectBotModal } from "../BotsListPanel";
import { ApiError, apiRequest } from "@/services/api";
import { brl, emptyInternational, type Block, type BlockType, type Bot, type Flow, type FlowDefinition, type FlowSummary, type International } from "../types";
import { MediaGrid } from "./MediaGrid";
import { RichTextEditor } from "./RichTextEditor";
import { Collapsible, Field, Panel, StylePicker, Switch } from "./ui";

export type SectionProps = { flowId: string; draft: FlowDefinition; set: (patch: Partial<FlowDefinition>) => void };

// ---------------------------------------------------------------- Bots

export function BotsSection({ flowId, draft, set }: SectionProps) {
  const queryClient = useQueryClient();
  const [connectOpen, setConnectOpen] = useState(false);
  const [pick, setPick] = useState("");
  const bots = useQuery({ queryKey: ["bots"], queryFn: () => apiRequest<{ bots: Bot[] }>("/api/bots"), retry: false });
  const flows = useQuery({ queryKey: ["bots", "flows"], queryFn: () => apiRequest<{ flows: Flow[] }>("/api/bots/flows/list"), retry: false });
  const summary = useQuery({
    queryKey: ["bots", "flow-summary", flowId],
    queryFn: () => apiRequest<FlowSummary>(`/api/bots/flows/${flowId}/summary`),
    retry: false,
    refetchInterval: 60_000,
  });
  const patch = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) => apiRequest<Bot>(`/api/bots/${id}`, { method: "PATCH", body }),
    onSuccess: () => {
      setPick("");
      void queryClient.invalidateQueries({ queryKey: ["bots"] });
    },
  });
  const all = bots.data?.bots ?? [];
  const linked = all.filter((bot) => bot.flow_id === flowId);
  const others = all.filter((bot) => bot.flow_id !== flowId);

  return (
    <div className="space-y-4">
      <Panel icon={<ListOrdered size={18} />} title="Resumo do fluxo">
        <dl className="grid grid-cols-3 gap-2 text-center">
          {[
            [<Users key="i" size={14} />, "Leads", String(summary.data?.leads ?? "—")],
            [<Crown key="i" size={14} />, "VIPs", String(summary.data?.vips ?? "—")],
            [<DollarSign key="i" size={14} />, "Receita", summary.data ? brl(summary.data.revenue) : "—"],
          ].map(([icon, label, value]) => (
            <div className="rounded-xl bg-surface-inset p-3" key={String(label)}>
              <dt className="flex items-center justify-center gap-1 text-[11px] uppercase tracking-wide text-muted">
                {icon}
                {label}
              </dt>
              <dd className="mt-1 text-base font-semibold text-fg sm:text-lg">{value}</dd>
            </div>
          ))}
        </dl>
      </Panel>

      <Panel
        icon={<BotIcon size={18} />}
        title="Bots vinculados"
        description="Os bots que executam este fluxo. Com vários, cada um atende seus próprios leads (bom contra quedas)."
        aside={<span className="text-xs text-muted">{linked.length} bot(s)</span>}
      >
        {patch.error && <p className="text-sm text-danger">{patch.error instanceof ApiError ? patch.error.message : "Não foi possível alterar o bot."}</p>}
        <ul className="space-y-2">
          {linked.map((bot) => (
            <li className="flex items-center gap-3 rounded-xl border border-line bg-surface-inset p-3" key={bot.id}>
              <span className="grid size-10 shrink-0 place-items-center rounded-full bg-brand-soft text-accent">
                <BotIcon size={18} />
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium text-fg">{bot.name}</p>
                <a className="text-xs text-accent hover:underline" href={`https://t.me/${bot.username}`} rel="noreferrer" target="_blank">
                  @{bot.username}
                </a>
                {bot.status === "error" && <p className="truncate text-xs text-danger">{bot.last_error ?? "Com erro"}</p>}
              </div>
              <Switch checked={bot.is_active} label={`Ativar @${bot.username}`} onChange={(is_active) => patch.mutate({ id: bot.id, body: { is_active } })} />
              <button
                aria-label={`Desvincular @${bot.username}`}
                className="btn-ghost !min-h-9 !px-2 text-danger"
                onClick={() => patch.mutate({ id: bot.id, body: { clear_flow: true } })}
                type="button"
              >
                <Trash2 size={15} />
              </button>
            </li>
          ))}
          {linked.length === 0 && <li className="text-sm text-muted">Nenhum bot executa este fluxo ainda.</li>}
        </ul>
        <div className="grid gap-2 rounded-xl border border-line-soft p-3">
          <p className="text-sm font-medium text-fg">Adicionar bot</p>
          <div className="flex gap-2">
            <select className="field min-w-0 flex-1" value={pick} onChange={(event) => setPick(event.target.value)}>
              <option value="">{others.length ? "Selecione um bot para adicionar" : "Nenhum outro bot conectado"}</option>
              {others.map((bot) => (
                <option key={bot.id} value={bot.id}>
                  @{bot.username}
                  {bot.flow_id ? " (sai do fluxo atual)" : ""}
                </option>
              ))}
            </select>
            <Button disabled={!pick || patch.isPending} onClick={() => patch.mutate({ id: pick, body: { flow_id: flowId } })} variant="primary">
              Adicionar
            </Button>
          </div>
          <button className="justify-self-start text-sm text-accent hover:underline" onClick={() => setConnectOpen(true)} type="button">
            + Conectar novo bot do @BotFather
          </button>
        </div>
      </Panel>

      <Panel icon={<MessageSquare size={18} />} title="@ Suporte (opcional)" description="Mostra o botão “💬 Suporte” na boas-vindas e no Pix.">
        <input
          className="field"
          maxLength={33}
          placeholder="@username"
          value={draft.support_username ? `@${draft.support_username.replace(/^@/, "")}` : ""}
          onChange={(event) => set({ support_username: event.target.value.replace(/[^A-Za-z0-9_]/g, "").slice(0, 32) || null })}
        />
      </Panel>
      <ConnectBotModal
        defaultFlowId={flowId}
        flows={flows.data?.flows ?? []}
        onClose={() => setConnectOpen(false)}
        onDone={() => void queryClient.invalidateQueries({ queryKey: ["bots"] })}
        open={connectOpen}
      />
    </div>
  );
}

// ---------------------------------------------------------------- Boas-vindas

const blockTypes: { value: BlockType; label: string; max: number }[] = [
  { value: "text", label: "Texto", max: 0 },
  { value: "photo", label: "Foto", max: 1 },
  { value: "video", label: "Vídeo", max: 1 },
  { value: "voice", label: "Áudio de voz", max: 1 },
  { value: "video_note", label: "Vídeo redondo", max: 1 },
  { value: "album", label: "Álbum (2 a 10)", max: 10 },
];

function move<T>(list: T[], index: number, delta: number): T[] {
  const target = index + delta;
  if (target < 0 || target >= list.length) return list;
  const copy = [...list];
  [copy[index], copy[target]] = [copy[target], copy[index]];
  return copy;
}

function ButtonsPreview({ draft }: { draft: FlowDefinition }) {
  const offer = draft.offer;
  const rows: { text: string; style: string }[] = offer.cta_enabled && draft.plans.length
    ? [{ text: offer.cta_label, style: offer.cta_style }]
    : draft.plans.map((plan) => ({ text: plan.button_text || `${plan.name} · ${brl(plan.price || 0)}`, style: plan.button_style }));
  offer.redirect_buttons.filter((item) => item.label).forEach((item) => rows.push({ text: `${item.label} ↗`, style: "default" }));
  if (draft.support_username) rows.push({ text: "💬 Suporte ↗", style: "default" });
  const color: Record<string, string> = {
    default: "bg-white/10 text-fg",
    primary: "bg-[#3b82f6]/80 text-white",
    success: "bg-[#22c55e]/80 text-white",
    danger: "bg-[#ef4444]/80 text-white",
  };
  if (!rows.length) return <p className="text-xs text-muted">Sem botões: adicione planos na seção Planos.</p>;
  return (
    <div className="mx-auto grid w-full max-w-sm gap-1.5 rounded-2xl bg-[#17212b] p-2">
      {rows.map((row, index) => (
        <span className={`rounded-lg px-3 py-2 text-center text-sm font-medium ${color[row.style] ?? color.default}`} key={index}>
          {row.text}
        </span>
      ))}
    </div>
  );
}

export function WelcomeSection({ draft, set }: SectionProps) {
  const offer = draft.offer;
  const setOffer = (patch: Partial<FlowDefinition["offer"]>) => set({ offer: { ...offer, ...patch } });
  const [openBlock, setOpenBlock] = useState<number | null>(null);
  const setBlock = (index: number, block: Block) => set({ welcome: draft.welcome.map((item, i) => (i === index ? block : item)) });

  return (
    <div className="space-y-4">
      <Panel title="Mídias" description="Enviadas antes da mensagem de boas-vindas (até 3: fotos, vídeos ou áudios).">
        <MediaGrid max={3} value={offer.media_ids} onChange={(media_ids) => setOffer({ media_ids })} />
        <label className="flex items-center justify-between gap-3 text-sm text-fg-2">
          <span>Borrar fotos e vídeos (spoiler: o lead toca para ver)</span>
          <Switch checked={offer.spoiler} label="Borrar mídias" onChange={(spoiler) => setOffer({ spoiler })} />
        </label>
      </Panel>

      <Panel title="Mensagem de boas-vindas">
        <RichTextEditor
          label="Mensagem"
          required
          value={offer.text}
          onChange={(text) => setOffer({ text })}
          hint={offer.media_ids.length === 1 ? "Com 1 mídia e até 1.024 caracteres, o texto vai como legenda da mídia." : undefined}
        />
      </Panel>

      <Panel
        icon={<MessageSquare size={18} />}
        title="Mensagem secundária"
        description="Mensagem separada, enviada logo depois, onde ficam os botões."
        aside={<Switch checked={offer.secondary_enabled} label="Mensagem secundária" onChange={(secondary_enabled) => setOffer({ secondary_enabled })} />}
      >
        {offer.secondary_enabled && (
          <RichTextEditor label="Texto da mensagem secundária" rows={3} value={offer.secondary_text} onChange={(secondary_text) => setOffer({ secondary_text })} />
        )}
      </Panel>

      <Panel
        icon={<MousePointerClick size={18} />}
        title="Botão CTA"
        description="Um único botão de chamada no lugar da lista de planos; ao tocar, o lead vê os planos."
        aside={<Switch checked={offer.cta_enabled} label="Botão CTA" onChange={(cta_enabled) => setOffer({ cta_enabled })} />}
      >
        {offer.cta_enabled && (
          <div className="grid gap-3">
            <Field label="Texto do botão">
              <input className="field" maxLength={64} value={offer.cta_label} onChange={(event) => setOffer({ cta_label: event.target.value })} />
            </Field>
            <StylePicker value={offer.cta_style} onChange={(cta_style) => setOffer({ cta_style })} />
            <RichTextEditor label="Mensagem que mostra os planos" rows={2} value={offer.plans_text} onChange={(plans_text) => setOffer({ plans_text })} />
          </div>
        )}
      </Panel>

      <Panel
        icon={<Link2 size={18} />}
        title="Botões redirect"
        description="Botões que abrem links externos (até 3), abaixo dos planos."
        aside={
          offer.redirect_buttons.length < 3 && (
            <button
              className="text-sm text-accent hover:underline"
              onClick={() => setOffer({ redirect_buttons: [...offer.redirect_buttons, { label: "", url: "https://" }] })}
              type="button"
            >
              + Adicionar
            </button>
          )
        }
      >
        {offer.redirect_buttons.length === 0 && <p className="text-sm italic text-muted">Nenhum botão redirect configurado.</p>}
        {offer.redirect_buttons.map((item, index) => (
          <div className="grid gap-2 sm:grid-cols-[1fr_1.4fr_auto]" key={index}>
            <input
              aria-label="Texto do botão"
              className="field"
              maxLength={64}
              placeholder="Texto do botão"
              value={item.label}
              onChange={(event) => setOffer({ redirect_buttons: offer.redirect_buttons.map((b, i) => (i === index ? { ...b, label: event.target.value } : b)) })}
            />
            <input
              aria-label="Link"
              className="field"
              placeholder="https://"
              value={item.url}
              onChange={(event) => setOffer({ redirect_buttons: offer.redirect_buttons.map((b, i) => (i === index ? { ...b, url: event.target.value } : b)) })}
            />
            <button
              aria-label="Remover botão"
              className="btn-ghost !min-h-10 !px-2 text-danger"
              onClick={() => setOffer({ redirect_buttons: offer.redirect_buttons.filter((_, i) => i !== index) })}
              type="button"
            >
              <Trash2 size={15} />
            </button>
          </div>
        ))}
      </Panel>

      <Panel title="Prévia dos botões" description="Como os botões aparecem no Telegram.">
        <ButtonsPreview draft={draft} />
      </Panel>

      <Panel
        title="Mensagens antes da boas-vindas (opcional)"
        description="Sequência enviada antes, com espera entre cada uma, para simular uma conversa."
        aside={<span className="text-xs text-muted">{draft.welcome.length}/30</span>}
      >
        <div className="space-y-2">
          {draft.welcome.map((block, index) => {
            const meta = blockTypes.find((item) => item.value === block.type)!;
            return (
              <Collapsible
                key={index}
                open={openBlock === index}
                onToggle={() => setOpenBlock(openBlock === index ? null : index)}
                title={`${index + 1}. ${meta.label}`}
                subtitle={index === 0 ? "enviada na hora do /start" : block.delay_seconds ? `espera ${block.delay_seconds}s` : "sem espera"}
                actions={
                  <span className="flex gap-1">
                    <button aria-label="Subir" className="btn-ghost !min-h-8 !px-2" disabled={index === 0} onClick={() => set({ welcome: move(draft.welcome, index, -1) })} type="button"><ArrowUp size={14} /></button>
                    <button aria-label="Descer" className="btn-ghost !min-h-8 !px-2" disabled={index === draft.welcome.length - 1} onClick={() => set({ welcome: move(draft.welcome, index, 1) })} type="button"><ArrowDown size={14} /></button>
                    <button aria-label="Remover" className="btn-ghost !min-h-8 !px-2 text-danger" onClick={() => set({ welcome: draft.welcome.filter((_, i) => i !== index) })} type="button"><Trash2 size={14} /></button>
                  </span>
                }
              >
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="Tipo">
                    <select className="field" value={block.type} onChange={(event) => setBlock(index, { ...block, type: event.target.value as BlockType, media_ids: [] })}>
                      {blockTypes.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                    </select>
                  </Field>
                  <Field label={index === 0 ? "Enviada na hora do /start" : "Esperar antes (segundos)"}>
                    <input className="field" disabled={index === 0} min={0} max={86400} type="number" value={index === 0 ? 0 : block.delay_seconds} onChange={(event) => setBlock(index, { ...block, delay_seconds: Math.max(0, Number(event.target.value) || 0) })} />
                  </Field>
                </div>
                {meta.max > 0 && (
                  <MediaGrid
                    kinds={block.type === "voice" ? ["audio"] : block.type === "photo" ? ["photo"] : block.type === "album" ? ["photo", "video"] : ["video"]}
                    max={meta.max}
                    value={block.media_ids}
                    onChange={(media_ids) => setBlock(index, { ...block, media_ids })}
                  />
                )}
                {block.type !== "voice" && block.type !== "video_note" && (
                  <RichTextEditor label={block.type === "text" ? "Texto" : "Legenda (opcional)"} max={1000} rows={3} value={block.text ?? ""} onChange={(text) => setBlock(index, { ...block, text })} />
                )}
              </Collapsible>
            );
          })}
        </div>
        <Button
          disabled={draft.welcome.length >= 30}
          onClick={() => {
            set({ welcome: [...draft.welcome, { type: "text", text: "", media_ids: [], spoiler: false, delay_seconds: 0 }] });
            setOpenBlock(draft.welcome.length);
          }}
          size="sm"
        >
          <Plus size={14} /> Adicionar mensagem
        </Button>
      </Panel>
    </div>
  );
}

// ---------------------------------------------------------------- International

type GatewayStateLite = { gateways: { id: string; name: string; available: boolean }[] };

/** Card/international sales (Stripe) and auto-translation, per funnel. The block can only be
 *  turned on when the admin has released the "Vendas Internacionais" gateway. */
export function InternationalSection({ draft, set }: SectionProps) {
  const gateways = useQuery({
    queryKey: ["payment-gateways"],
    queryFn: () => apiRequest<GatewayStateLite>("/api/payment-gateways"),
    retry: false,
  });
  const stripe = gateways.data?.gateways.find((item) => item.id === "stripe");
  const stripeReady = Boolean(stripe?.available);
  const intl = draft.international ?? emptyInternational();
  const setIntl = (patch: Partial<International>) => set({ international: { ...intl, ...patch } });
  // Enabling defaults to USD so the server (which needs a currency or translation on) accepts it.
  const toggle = (on: boolean) =>
    setIntl(on ? { enabled: true, currencies: intl.currencies.length ? intl.currencies : ["USD"] } : { enabled: false });
  const setPriceUsd = (index: number, raw: string) =>
    set({ plans: draft.plans.map((plan, i) => (i === index ? { ...plan, price_usd: raw.replace(/[^\d.,]/g, "") || null } : plan)) });

  return (
    <div className="space-y-4">
      <Panel
        icon={<Globe size={18} />}
        title="Vendas Internacionais"
        description="Venda no cartão (Stripe) em dólar e, se quiser, traduza a copy para o idioma do lead. O Pix em BRL continua funcionando igual."
        aside={
          stripeReady ? (
            <Switch checked={intl.enabled} onChange={toggle} label="Ativar vendas internacionais" />
          ) : (
            <span className="rounded-full bg-well px-2 py-0.5 text-[11px] text-muted">Indisponível</span>
          )
        }
      >
        {!stripeReady && (
          <p className="rounded-xl border border-warning/40 bg-warning/10 px-3 py-2 text-xs leading-5 text-warning">
            Para usar, o administrador precisa liberar <b>Vendas Internacionais</b> em Gateways de pagamento. Enquanto não liberar, este bloco fica desativado.
          </p>
        )}

        {stripeReady && intl.enabled && (
          <div className="space-y-4">
            <Field label="Moeda do cartão" hint="Além do Pix em BRL, o lead pode escolher pagar no cartão em dólar.">
              <span className="inline-flex w-fit items-center rounded-full border border-brand bg-brand-soft px-4 py-2 text-xs font-medium text-accent">
                USD · Dólar
              </span>
            </Field>

            <Field label="Preço no cartão">
              <div className="grid gap-2 sm:grid-cols-2">
                {(
                  [
                    ["variable", "Converter do BRL", "Usa o preço em reais e converte pela cotação."],
                    ["fixed", "Preço fixo em US$", "Você define o valor em dólar de cada plano."],
                  ] as const
                ).map(([value, title, desc]) => (
                  <button
                    aria-checked={intl.pricing === value}
                    className={`rounded-xl border p-3 text-left ${intl.pricing === value ? "border-brand bg-brand-soft" : "border-line hover:border-brand"}`}
                    key={value}
                    onClick={() => setIntl({ pricing: value })}
                    role="radio"
                    type="button"
                  >
                    <span className="block text-sm font-medium text-fg">{title}</span>
                    <span className="mt-0.5 block text-xs text-muted">{desc}</span>
                  </button>
                ))}
              </div>
            </Field>

            {intl.pricing === "variable" ? (
              <Field label="Cotação (R$ por US$ 1)" hint="Ex.: 5,00 → um plano de R$ 50 sai por US$ 10 no cartão.">
                <input
                  className="field !w-40"
                  inputMode="decimal"
                  value={intl.usd_rate}
                  onChange={(event) => setIntl({ usd_rate: event.target.value.replace(/[^\d.,]/g, "") })}
                />
              </Field>
            ) : (
              <div className="space-y-2">
                <p className="text-sm text-fg-2">Preço em dólar de cada plano</p>
                {draft.plans.length === 0 ? (
                  <p className="text-xs text-muted">Crie planos na seção Planos primeiro.</p>
                ) : (
                  draft.plans.map((plan, index) => (
                    <div className="flex items-center gap-3 rounded-xl border border-line-soft p-2.5" key={plan.id}>
                      <span className="min-w-0 flex-1 truncate text-sm text-fg">
                        {plan.name || `Plano ${index + 1}`} <span className="text-muted">· {brl(plan.price)}</span>
                      </span>
                      <span className="flex items-center gap-1 text-sm text-muted">
                        US$
                        <input
                          aria-label={`Preço em dólar de ${plan.name || `plano ${index + 1}`}`}
                          className="field !w-24"
                          inputMode="decimal"
                          placeholder="0.00"
                          value={plan.price_usd ?? ""}
                          onChange={(event) => setPriceUsd(index, event.target.value)}
                        />
                      </span>
                    </div>
                  ))
                )}
              </div>
            )}

            <div className="flex items-start justify-between gap-3 rounded-xl border border-line-soft p-3">
              <span className="min-w-0">
                <span className="flex items-center gap-2 text-sm font-medium text-fg">
                  <Languages size={15} /> Traduzir automaticamente
                </span>
                <span className="mt-0.5 block text-xs leading-5 text-muted">
                  Traduz a copy do funil para o idioma do lead (pelo idioma do Telegram dele). Quem estiver em português recebe o texto original.
                </span>
              </span>
              <Switch checked={intl.translate} onChange={(on) => setIntl({ translate: on })} label="Ativar tradução automática" />
            </div>

            <p className="rounded-xl border border-line-soft px-3 py-2 text-[11px] leading-5 text-muted">
              Lembre de deixar <b>Vendas Internacionais</b> ligada na prioridade de gateways e <b>salvar o fluxo</b> para valer no bot.
            </p>
          </div>
        )}
      </Panel>
    </div>
  );
}
