import { useEffect, useState, type ComponentType, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  BarChart3,
  CalendarDays,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleDollarSign,
  ClipboardCheck,
  ExternalLink,
  Megaphone,
  MessageSquare,
  Package,
  Plus,
  QrCode,
  Save,
  Sparkles,
  Trash2,
  UserCheck,
  Users,
  X,
  Zap,
} from "lucide-react";

import { confirmAction } from "@/lib/confirm";
import { ApiError, apiRequest } from "@/services/api";
import { cleanBump, cleanDelivery, money } from "../FlowEditor";
import { BumpEditor, DeliveryEditor } from "../editor/DeliveryEditor";
import { MediaGrid } from "../editor/MediaGrid";
import { BASE_VARIABLES, RichTextEditor } from "../editor/RichTextEditor";
import { DurationSelect, Field, MoneyInput, StylePicker, Switch } from "../editor/ui";
import {
  brl,
  emptyBump,
  emptyCampaignDefinition,
  emptyDelivery,
  type Campaign,
  type CampaignDefinition,
  type CampaignMessage,
  type CampaignPeriod,
  type CampaignPlan,
  type CampaignTarget,
  type Flow,
} from "../types";
import { CampaignStats } from "./CampaignStats";

export const TARGETS: { value: CampaignTarget; label: string; summary: string; icon: ComponentType<{ size?: number }> }[] = [
  { value: "all", label: "Todos os Leads", summary: "Todos os leads", icon: Users },
  { value: "not_bought", label: "Não Compraram", summary: "Quem ainda não comprou", icon: AlertCircle },
  { value: "bought", label: "Já Compraram", summary: "Quem já comprou", icon: CheckCircle2 },
  { value: "pix_generated", label: "PIX Gerado", summary: "Gerou o Pix e não pagou", icon: QrCode },
  { value: "vip_expired", label: "VIP Expirado", summary: "Acesso VIP vencido", icon: CalendarDays },
  { value: "group_members", label: "Membros de Grupo", summary: "VIP ativo no grupo", icon: UserCheck },
];

const PERIODS: { value: CampaignPeriod; label: string }[] = [
  { value: "total", label: "Total" },
  { value: "today", label: "Hoje" },
  { value: "yesterday", label: "Ontem" },
  { value: "7d", label: "7 dias" },
  { value: "30d", label: "30 dias" },
  { value: "custom", label: "Escolher" },
];

const STEPS = [
  {
    id: "campaign",
    label: "Campanha e fluxo",
    icon: Megaphone,
    description: "Dê um nome claro e escolha em qual fluxo a campanha será executada.",
    tips: ["Confirme o nome da campanha", "Confira o fluxo e os bots vinculados"],
  },
  {
    id: "audience",
    label: "Público",
    icon: Users,
    description: "Defina quem deve receber a campanha e confira o alcance estimado.",
    tips: ["Revise a segmentação", "Confira o alcance estimado"],
  },
  {
    id: "message",
    label: "Mensagem",
    icon: MessageSquare,
    description: "Monte o conteúdo, as mídias, os botões e as variantes da comunicação.",
    tips: ["Revise o texto e as variantes", "Confira mídias e botões"],
  },
  {
    id: "offer",
    label: "Oferta e entrega",
    icon: CircleDollarSign,
    description: "Configure preços, destino da entrega, order bump e redirecionamento.",
    tips: ["Revise valores e formas de entrega", "Confira order bump e redirecionamento"],
  },
  {
    id: "review",
    label: "Revisar e salvar",
    icon: ClipboardCheck,
    description: "Confira a campanha completa antes de criar ou salvar as alterações.",
    tips: ["Confira o resumo completo", "Salve as alterações quando estiver pronto"],
  },
] as const;

const NEXT_LABELS = ["Definir público", "Montar mensagem", "Revisar oferta", "Ver revisão final"];

function emptyMessage(): CampaignMessage {
  return { text: "", media_ids: [], spoiler: false, buttons: [] };
}

function payload(definition: CampaignDefinition): CampaignDefinition {
  const custom = definition.audience.period === "custom";
  return {
    audience: { ...definition.audience, start: custom ? definition.audience.start || null : null, end: custom ? definition.audience.end || null : null },
    messages: definition.messages.map((message) => ({
      ...message,
      buttons: message.buttons.filter((item) => item.label.trim() && item.url.trim()),
    })),
    offer: {
      plans: definition.offer.plans.map((plan) => ({ ...plan, price: money(plan.price), delivery: cleanDelivery(plan.delivery) })),
      order_bump: cleanBump(definition.offer.order_bump),
      redirect: definition.offer.redirect && definition.offer.redirect.label.trim() && definition.offer.redirect.url.trim() ? definition.offer.redirect : null,
    },
  };
}

export function CampaignEditor({
  campaign,
  flows,
  defaultFlowId,
  onClose,
}: {
  campaign: Campaign | null;
  flows: Flow[];
  defaultFlowId: string | null;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [current, setCurrent] = useState(0);
  const [name, setName] = useState(campaign?.name ?? "");
  const [flowId, setFlowId] = useState(campaign?.flow_id ?? defaultFlowId ?? flows[0]?.id ?? "");
  const [definition, setDefinition] = useState<CampaignDefinition>(() => {
    const base = emptyCampaignDefinition();
    const saved = campaign?.definition;
    return saved ? { ...base, ...saved, audience: { ...base.audience, ...saved.audience }, offer: { ...base.offer, ...saved.offer } } : base;
  });
  const [variant, setVariant] = useState(0);
  const [stats, setStats] = useState(false);
  const [initial] = useState(() => JSON.stringify([name, flowId, definition]));
  const dirty = JSON.stringify([name, flowId, definition]) !== initial;
  const flow = flows.find((item) => item.id === flowId);

  // Plans of the funnel to copy from (protected copies keep their content hidden).
  const flowDetail = useQuery({
    queryKey: ["bots", "flow", flowId],
    queryFn: () => apiRequest<Flow>(`/api/bots/flows/${flowId}`),
    enabled: Boolean(flowId) && !flow?.protected,
    retry: false,
  });
  const flowPlans = flowDetail.data?.definition?.plans ?? [];
  const hasDefaultDelivery = Boolean(flowDetail.data?.definition?.default_delivery);

  const audienceKey = JSON.stringify(payload(definition).audience);
  const estimate = useQuery({
    queryKey: ["bots", "campaign-estimate", flowId, audienceKey],
    queryFn: () =>
      apiRequest<{ reach: number; blocked: number }>("/api/bots/campaigns/estimate", {
        method: "POST",
        body: { flow_id: flowId, audience: payload(definition).audience },
      }),
    enabled: Boolean(flowId) && (definition.audience.period !== "custom" || Boolean(definition.audience.start && definition.audience.end)),
    retry: false,
    placeholderData: (previous) => previous,
  });

  const save = useMutation({
    mutationFn: async (andSend: boolean) => {
      const body = { name: name.trim(), flow_id: flowId, definition: payload(definition) };
      const saved = campaign
        ? await apiRequest<Campaign>(`/api/bots/campaigns/${campaign.id}`, { method: "PUT", body })
        : await apiRequest<Campaign>("/api/bots/campaigns", { method: "POST", body });
      return andSend ? apiRequest<Campaign>(`/api/bots/campaigns/${saved.id}/send`, { method: "POST" }) : saved;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["bots", "campaigns"] });
      onClose();
    },
  });

  useEffect(() => {
    // The global refresh button steps aside, like in the flow editor.
    document.body.dataset.flowEditor = "1";
    return () => {
      delete document.body.dataset.flowEditor;
    };
  }, []);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const setAudience = (patch: Partial<CampaignDefinition["audience"]>) => setDefinition({ ...definition, audience: { ...definition.audience, ...patch } });
  const setOffer = (patch: Partial<CampaignDefinition["offer"]>) => setDefinition({ ...definition, offer: { ...definition.offer, ...patch } });
  const message = definition.messages[Math.min(variant, definition.messages.length - 1)];
  const setMessage = (patch: Partial<CampaignMessage>) =>
    setDefinition({ ...definition, messages: definition.messages.map((item, index) => (index === variant ? { ...item, ...patch } : item)) });
  const setPlan = (index: number, patch: Partial<CampaignPlan>) =>
    setOffer({ plans: definition.offer.plans.map((item, i) => (i === index ? { ...item, ...patch } : item)) });

  const target = TARGETS.find((item) => item.value === definition.audience.target) ?? TARGETS[1];
  const missingDefault = !hasDefaultDelivery && !flow?.protected && definition.offer.plans.some((plan) => !plan.delivery);
  const problems = [
    [!name.trim() || !flowId, "Dê um nome e escolha o fluxo."],
    [definition.audience.period === "custom" && !(definition.audience.start && definition.audience.end), "Escolha as datas do período."],
    [definition.messages.some((item) => !item.text.trim()), "Toda variante precisa de texto."],
    [missingDefault, "Um plano usa a entrega padrão, mas o fluxo não tem entrega padrão."],
  ] as const;
  const done = [
    Boolean(name.trim() && flowId),
    definition.audience.period !== "custom" || Boolean(definition.audience.start && definition.audience.end),
    definition.messages.every((item) => item.text.trim()),
    !missingDefault,
  ];
  const ready = problems.every(([bad]) => !bad);
  const summaries = [
    name.trim() ? `${name.trim()} · ${flow?.name ?? "sem fluxo"}` : "",
    `${target.summary} · ${estimate.data ? estimate.data.reach.toLocaleString("pt-BR") : "…"}`,
    `${definition.messages.length} mensage${definition.messages.length > 1 ? "ns" : "m"}`,
    definition.offer.plans.length ? `${definition.offer.plans.length} plano(s)` : "Sem plano",
  ];
  const progress = Math.round(((current + 1) / STEPS.length) * 100);
  const step = STEPS[current];
  const close = async () => {
    if (!dirty || (await confirmAction("Sair sem salvar? As alterações desta campanha serão perdidas."))) onClose();
  };

  // Full screen above the app shell (a portal escapes the page's transformed containers).
  return createPortal(
    <div className="fixed inset-0 z-[60] flex flex-col bg-[var(--nm-bg)]">
      <header className="relative flex items-center gap-3 border-b border-line px-3 py-2.5 sm:px-5">
        <button aria-label="Etapa anterior" className="btn-secondary !min-h-10 !px-3" onClick={() => (current ? setCurrent(current - 1) : void close())} type="button">
          <ChevronLeft size={18} />
        </button>
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-accent">
            Remarketing <span className="text-muted">· {current + 1}/{STEPS.length}</span>
          </p>
          <p className="truncate font-semibold text-fg">{name.trim() || "Nova campanha"}</p>
          <p className="hidden truncate text-xs text-muted sm:block">Revise as configurações da campanha sem perder o contexto.</p>
        </div>
        {campaign && (
          <button aria-label="Ver estatísticas" className="btn-secondary !min-h-10 !px-3" onClick={() => setStats(true)} type="button">
            <BarChart3 size={17} />
          </button>
        )}
        <button className="btn-primary !min-h-10" disabled={!ready || save.isPending} onClick={() => save.mutate(false)} type="button">
          <Save size={16} /> {save.isPending ? "Salvando…" : "Salvar"}
        </button>
        <button aria-label="Fechar" className="btn-ghost !min-h-10 !px-2" onClick={() => void close()} type="button">
          <X size={18} />
        </button>
        <span className="absolute inset-x-0 bottom-0 h-0.5 bg-brand transition-all" style={{ width: `${progress}%` }} />
      </header>

      <div className="grid min-h-0 flex-1 lg:grid-cols-[320px_minmax(0,1fr)]">
        <aside className="hidden min-h-0 flex-col border-r border-line p-4 lg:flex">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted">Mapa da campanha</p>
          <p className="mb-3 text-xs text-muted">Revise cada etapa e salve quando tudo estiver pronto.</p>
          <ol className="grid gap-2 overflow-y-auto">
            {STEPS.map((item, index) => {
              const Icon = item.icon;
              const active = index === current;
              const ok = index < 4 && done[index];
              return (
                <li key={item.id}>
                  <button
                    className={`w-full rounded-2xl border p-3 text-left transition ${active ? "border-brand/60 bg-brand-soft" : "border-line bg-surface hover:border-line-soft"}`}
                    onClick={() => setCurrent(index)}
                    type="button"
                  >
                    <span className="flex items-center gap-3">
                      <span className={`grid size-8 shrink-0 place-items-center rounded-lg ${ok && !active ? "bg-success-soft text-success" : "bg-well text-fg-2"}`}>
                        {ok && !active ? <Check size={15} /> : <Icon size={15} />}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-medium text-fg">{item.label}</span>
                        {!active && index < 4 && summaries[index] && <span className="block truncate text-xs text-success">{summaries[index]}</span>}
                      </span>
                      <ChevronRight className="text-muted" size={15} />
                    </span>
                    {active && (
                      <span className="mt-2 block border-t border-line-soft pt-2 text-xs leading-5 text-muted">
                        {item.description}
                        {item.tips.map((tip) => (
                          <span className="mt-1 block text-accent" key={tip}>
                            • {tip}
                          </span>
                        ))}
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ol>
          <div className="mt-auto rounded-xl border border-line p-3">
            <p className="flex justify-between text-[10px] font-semibold uppercase tracking-[0.18em] text-muted">
              Progresso <span>{progress}%</span>
            </p>
            <div className="mt-2 h-1.5 rounded-full bg-well">
              <div className="h-1.5 rounded-full bg-brand transition-all" style={{ width: `${progress}%` }} />
            </div>
          </div>
        </aside>

        <div className="flex min-h-0 flex-col">
          <div className="flex gap-1.5 overflow-x-auto border-b border-line px-3 py-2 lg:hidden">
            {STEPS.map((item, index) => (
              <button
                className={`min-h-9 shrink-0 rounded-full px-3 text-xs font-medium ${index === current ? "bg-brand text-white" : index < 4 && done[index] ? "bg-success-soft text-success" : "bg-well text-muted"}`}
                key={item.id}
                onClick={() => setCurrent(index)}
                type="button"
              >
                {index + 1}. {item.label}
              </button>
            ))}
          </div>
          <main className="min-h-0 flex-1 overflow-y-auto px-3 py-5 sm:px-6">
            <div className="mx-auto grid max-w-4xl gap-4">
              {current === 0 && (
                <Box icon={<Sparkles size={18} />} title="Campanha e fluxo">
                  <Field label="Nome da campanha *">
                    <input className="field" maxLength={120} placeholder="Ex.: Volta dos não pagantes" value={name} onChange={(event) => setName(event.target.value)} />
                  </Field>
                  <Field label="Fluxo *" hint="A campanha vai para os leads deste fluxo, cada um pelo bot onde entrou.">
                    <select className="field" value={flowId} onChange={(event) => setFlowId(event.target.value)}>
                      {flows.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.name}
                          {item.bots ? ` · ${item.bots} bot(s)` : ""}
                        </option>
                      ))}
                    </select>
                  </Field>
                </Box>
              )}

              {current === 1 && (
                <Box icon={<Users size={18} />} title="Público da campanha">
                  <div className="flex items-center gap-3 rounded-2xl border border-line bg-surface-inset p-4">
                    <span className="grid size-10 place-items-center rounded-full bg-brand-soft text-accent">
                      <Users size={18} />
                    </span>
                    <span>
                      <span className="block text-xs text-muted">Alcance estimado</span>
                      <span className="text-2xl font-semibold text-fg">{estimate.data ? estimate.data.reach.toLocaleString("pt-BR") : "…"}</span>{" "}
                      <span className="text-sm text-muted">leads</span>
                      {estimate.data && estimate.data.blocked > 0 && (
                        <span className="block text-xs text-muted">{estimate.data.blocked.toLocaleString("pt-BR")} já bloquearam o bot e ficam de fora</span>
                      )}
                    </span>
                  </div>
                  <div className="grid gap-2 rounded-2xl border border-line bg-surface-inset p-4">
                    <p className="flex items-center gap-2 text-sm font-medium text-fg">
                      <CalendarDays size={15} /> Período <span className="text-xs font-normal text-muted">· data de entrada do lead</span>
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {PERIODS.map((item) => (
                        <button
                          className={`min-h-9 rounded-lg border px-3 text-xs font-medium ${definition.audience.period === item.value ? "border-brand bg-brand-soft text-accent" : "border-line text-fg-2"}`}
                          key={item.value}
                          onClick={() => setAudience({ period: item.value })}
                          type="button"
                        >
                          {item.label}
                        </button>
                      ))}
                    </div>
                    {definition.audience.period === "custom" && (
                      <div className="grid gap-2 sm:grid-cols-2">
                        <Field label="De">
                          <input className="field" type="date" value={definition.audience.start ?? ""} onChange={(event) => setAudience({ start: event.target.value })} />
                        </Field>
                        <Field label="Até">
                          <input className="field" type="date" value={definition.audience.end ?? ""} onChange={(event) => setAudience({ end: event.target.value })} />
                        </Field>
                      </div>
                    )}
                  </div>
                  <p className="text-sm font-medium text-fg">Público-alvo *</p>
                  <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                    {TARGETS.map((item) => {
                      const Icon = item.icon;
                      const on = definition.audience.target === item.value;
                      return (
                        <button
                          aria-pressed={on}
                          className={`flex min-h-14 items-center gap-3 rounded-xl border px-4 text-left text-sm font-medium transition ${on ? "border-warning bg-warning-soft text-warning" : "border-line bg-surface-inset text-fg hover:border-line-soft"}`}
                          key={item.value}
                          onClick={() => setAudience({ target: item.value })}
                          type="button"
                        >
                          <Icon size={17} /> {item.label}
                        </button>
                      );
                    })}
                  </div>
                </Box>
              )}

              {current === 2 && (
                <Box
                  icon={<MessageSquare size={18} />}
                  title="Conteúdo da mensagem"
                  aside={
                    definition.messages.length < 3 && (
                      <button
                        className="flex items-center gap-1 text-xs font-medium text-accent"
                        onClick={() => {
                          setDefinition({ ...definition, messages: [...definition.messages, { ...emptyMessage(), text: message.text }] });
                          setVariant(definition.messages.length);
                        }}
                        type="button"
                      >
                        <Plus size={14} /> Adicionar variante
                      </button>
                    )
                  }
                >
                  {definition.messages.length > 1 && (
                    <div className="flex flex-wrap items-center gap-2">
                      {definition.messages.map((_, index) => (
                        <button
                          className={`min-h-9 rounded-full border px-4 text-xs font-medium ${index === variant ? "border-brand bg-brand-soft text-accent" : "border-line text-muted"}`}
                          key={index}
                          onClick={() => setVariant(index)}
                          type="button"
                        >
                          Variante {String.fromCharCode(65 + index)}
                        </button>
                      ))}
                      <button
                        aria-label="Remover esta variante"
                        className="btn-ghost !min-h-9 !px-2 text-danger"
                        onClick={() => {
                          setDefinition({ ...definition, messages: definition.messages.filter((_, index) => index !== variant) });
                          setVariant(0);
                        }}
                        type="button"
                      >
                        <Trash2 size={15} />
                      </button>
                      <span className="text-xs text-muted">As variantes se alternam entre os leads.</span>
                    </div>
                  )}
                  <RichTextEditor key={variant} label="Mensagem" required rows={5} value={message.text} variables={BASE_VARIABLES} onChange={(text) => setMessage({ text })} />
                  <MediaGrid key={`m${variant}`} max={3} title="Mídia (opcional)" value={message.media_ids} onChange={(media_ids) => setMessage({ media_ids })} />
                  <label className="flex items-center justify-between gap-3 rounded-xl border border-line-soft p-3 text-sm text-fg-2">
                    <span>Mídias com spoiler (borradas até tocar)</span>
                    <Switch checked={message.spoiler} label="Spoiler" onChange={(spoiler) => setMessage({ spoiler })} />
                  </label>
                  <div className="grid gap-2">
                    <div className="flex items-center justify-between text-sm font-medium text-fg">
                      Botões de link (opcional)
                      {message.buttons.length < 3 && (
                        <button
                          className="flex items-center gap-1 text-xs font-medium text-accent"
                          onClick={() => setMessage({ buttons: [...message.buttons, { label: "", url: "" }] })}
                          type="button"
                        >
                          <Plus size={14} /> Adicionar botão
                        </button>
                      )}
                    </div>
                    {message.buttons.map((item, index) => (
                      <div className="grid gap-2 sm:grid-cols-[1fr_1.4fr_auto]" key={index}>
                        <input
                          aria-label="Texto do botão"
                          className="field"
                          maxLength={64}
                          placeholder="Texto do botão"
                          value={item.label}
                          onChange={(event) => setMessage({ buttons: message.buttons.map((b, i) => (i === index ? { ...b, label: event.target.value } : b)) })}
                        />
                        <input
                          aria-label="Link do botão"
                          className="field"
                          placeholder="https://"
                          value={item.url}
                          onChange={(event) => setMessage({ buttons: message.buttons.map((b, i) => (i === index ? { ...b, url: event.target.value } : b)) })}
                        />
                        <button
                          aria-label="Remover botão"
                          className="btn-ghost !min-h-11 !px-2 text-danger"
                          onClick={() => setMessage({ buttons: message.buttons.filter((_, i) => i !== index) })}
                          type="button"
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>
                    ))}
                  </div>
                </Box>
              )}

              {current === 3 && (
                <>
                  <Box
                    icon={<Package size={18} />}
                    title="Planos de pagamento"
                    aside={
                      <button
                        className="btn-primary btn-sm"
                        disabled={definition.offer.plans.length >= 10}
                        onClick={() =>
                          setOffer({ plans: [...definition.offer.plans, { name: "Oferta especial", price: "9.90", duration_days: 30, delivery: null, button_style: "success" }] })
                        }
                        type="button"
                      >
                        <Plus size={14} /> Criar novo plano
                      </button>
                    }
                  >
                    {flowPlans.length > 0 && (
                      <div className="grid gap-2">
                        <p className="text-xs text-muted">Clique para adicionar um plano existente:</p>
                        <div className="grid gap-2 sm:grid-cols-2">
                          {flowPlans.map((plan) => (
                            <button
                              className="flex items-center justify-between gap-2 rounded-xl border border-line bg-surface-inset px-3 py-2 text-left hover:border-brand"
                              disabled={definition.offer.plans.length >= 10}
                              key={plan.id}
                              onClick={() =>
                                setOffer({
                                  plans: [
                                    ...definition.offer.plans,
                                    { name: plan.name, price: plan.price, duration_days: plan.duration_days, delivery: plan.delivery ?? null, button_style: plan.button_style === "default" ? "success" : plan.button_style },
                                  ],
                                })
                              }
                              type="button"
                            >
                              <span className="min-w-0">
                                <span className="block truncate text-sm font-medium text-fg">{plan.name}</span>
                                <span className="text-xs text-muted">{brl(plan.price)}</span>
                              </span>
                              <Plus className="shrink-0 text-muted" size={15} />
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                    {definition.offer.plans.length === 0 && (
                      <p className="rounded-xl border border-dashed border-line p-4 text-center text-sm text-muted">
                        Sem plano, a campanha manda só a mensagem (e os botões de link).
                      </p>
                    )}
                    {definition.offer.plans.map((plan, index) => (
                      <div className="grid gap-3 rounded-2xl border border-line bg-surface-inset p-3 sm:p-4" key={index}>
                        <div className="grid gap-3 sm:grid-cols-[1.4fr_1fr_auto] sm:items-end">
                          <Field label="Nome">
                            <input className="field" maxLength={60} value={plan.name} onChange={(event) => setPlan(index, { name: event.target.value })} />
                          </Field>
                          <MoneyInput value={plan.price} onChange={(price) => setPlan(index, { price })} />
                          <button
                            aria-label="Remover plano"
                            className="btn-ghost !min-h-11 !px-2 text-danger"
                            onClick={() => setOffer({ plans: definition.offer.plans.filter((_, i) => i !== index) })}
                            type="button"
                          >
                            <Trash2 size={15} />
                          </button>
                        </div>
                        <DurationSelect value={plan.duration_days} onChange={(duration_days) => setPlan(index, { duration_days })} />
                        <Field label="Entrega">
                          <select
                            className="field"
                            value={plan.delivery ? "own" : "default"}
                            onChange={(event) => setPlan(index, { delivery: event.target.value === "own" ? emptyDelivery("group") : null })}
                          >
                            <option value="default">Usar padrão do fluxo</option>
                            <option value="own">Entrega própria deste plano</option>
                          </select>
                        </Field>
                        {plan.delivery && <DeliveryEditor value={plan.delivery} onChange={(delivery) => setPlan(index, { delivery })} />}
                        <StylePicker value={plan.button_style} onChange={(button_style) => setPlan(index, { button_style })} />
                      </div>
                    ))}
                    {missingDefault && <p className="text-xs text-warning">Este fluxo não tem entrega padrão: escolha uma entrega própria para cada plano.</p>}
                  </Box>
                  <ToggleBox
                    checked={Boolean(definition.offer.order_bump)}
                    description="Oferta adicional específica para esta campanha, antes de gerar o Pix."
                    icon={<Zap size={18} />}
                    onChange={(on) => setOffer({ order_bump: on ? definition.offer.order_bump ?? emptyBump() : null })}
                    title="Order bump do remarketing"
                  >
                    {definition.offer.order_bump && <BumpEditor value={definition.offer.order_bump} onChange={(order_bump) => setOffer({ order_bump })} />}
                  </ToggleBox>
                  <ToggleBox
                    checked={Boolean(definition.offer.redirect)}
                    description="Botão que leva para um canal de prévias ou outro link (sem pagamento)."
                    icon={<ExternalLink size={18} />}
                    onChange={(on) => setOffer({ redirect: on ? definition.offer.redirect ?? { label: "👀 Ver prévias", url: "" } : null })}
                    title="Botão redirect"
                  >
                    {definition.offer.redirect && (
                      <div className="grid gap-2 sm:grid-cols-2">
                        <Field label="Texto do botão">
                          <input
                            className="field"
                            maxLength={64}
                            value={definition.offer.redirect.label}
                            onChange={(event) => setOffer({ redirect: { ...definition.offer.redirect!, label: event.target.value } })}
                          />
                        </Field>
                        <Field label="Link">
                          <input
                            className="field"
                            placeholder="https://t.me/..."
                            value={definition.offer.redirect.url}
                            onChange={(event) => setOffer({ redirect: { ...definition.offer.redirect!, url: event.target.value } })}
                          />
                        </Field>
                      </div>
                    )}
                  </ToggleBox>
                </>
              )}

              {current === 4 && (
                <div className="grid gap-4">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-accent">Revisão final</p>
                    <h2 className="text-xl font-semibold text-fg">Confira antes de salvar</h2>
                    <p className="text-sm text-muted">As alterações só valem quando você salvar a campanha.</p>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <ReviewCard icon={<Megaphone size={16} />} label="Campanha e fluxo" onEdit={() => setCurrent(0)} title={name.trim() || "Sem nome"} detail={flow?.name ?? "—"} />
                    <ReviewCard
                      icon={<Users size={16} />}
                      label="Público"
                      onEdit={() => setCurrent(1)}
                      title={target.summary}
                      detail={`${estimate.data ? estimate.data.reach.toLocaleString("pt-BR") : "…"} leads estimados · ${PERIODS.find((p) => p.value === definition.audience.period)?.label}`}
                    />
                    <ReviewCard
                      icon={<MessageSquare size={16} />}
                      label="Mensagem"
                      onEdit={() => setCurrent(2)}
                      title={summaries[2]}
                      detail={`${definition.messages[0].text.length} caracteres na variante A`}
                    />
                    <ReviewCard
                      icon={<Package size={16} />}
                      label="Oferta e entrega"
                      onEdit={() => setCurrent(3)}
                      title={summaries[3]}
                      detail={[
                        definition.offer.plans.map((plan) => `${plan.name} ${brl(plan.price || 0)}`).join(" · "),
                        definition.offer.order_bump && "order bump",
                        definition.offer.redirect && "redirect",
                      ]
                        .filter(Boolean)
                        .join(" · ") || "Só mensagem"}
                    />
                  </div>
                  {ready ? (
                    <p className="rounded-xl border border-success/30 bg-success-soft px-4 py-3 text-sm text-success">Tudo certo. A campanha está pronta para ser salva.</p>
                  ) : (
                    <ul className="rounded-xl border border-warning/30 bg-warning-soft px-4 py-3 text-sm text-warning">
                      {problems.filter(([bad]) => bad).map(([, text]) => (
                        <li key={text}>• {text}</li>
                      ))}
                    </ul>
                  )}
                  {campaign && (
                    <button className="flex items-center gap-3 rounded-2xl border border-line bg-surface p-4 text-left hover:border-line-soft" onClick={() => setStats(true)} type="button">
                      <span className="grid size-9 place-items-center rounded-lg bg-brand-soft text-accent">
                        <BarChart3 size={16} />
                      </span>
                      <span className="flex-1">
                        <span className="block text-sm font-medium text-fg">Ver estatísticas</span>
                        <span className="text-xs text-muted">
                          {campaign.sent.toLocaleString("pt-BR")} enviados · {brl(campaign.revenue)} receita · {campaign.runs} disparo(s)
                        </span>
                      </span>
                      <ChevronRight className="text-muted" size={16} />
                    </button>
                  )}
                  {save.error && (
                    <p className="rounded-xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-danger" role="alert">
                      {save.error instanceof ApiError ? save.error.message : "Não foi possível salvar."}
                    </p>
                  )}
                </div>
              )}
            </div>
          </main>
          <footer className="flex items-center gap-3 border-t border-line px-3 py-3 sm:px-6">
            <button className="btn-secondary !min-h-11" disabled={current === 0} onClick={() => setCurrent(current - 1)} type="button">
              <ChevronLeft size={16} /> Voltar
            </button>
            <p className="hidden flex-1 text-center text-xs text-muted md:block">{step.description}</p>
            <span className="flex-1 md:hidden" />
            {current < STEPS.length - 1 ? (
              <button className="btn-primary !min-h-11" onClick={() => setCurrent(current + 1)} type="button">
                {NEXT_LABELS[current]} <ChevronRight size={16} />
              </button>
            ) : (
              <span className="flex gap-2">
                <button className="btn-secondary !min-h-11" disabled={!ready || save.isPending} onClick={() => save.mutate(false)} type="button">
                  {campaign ? "Salvar alterações" : "Criar campanha"}
                </button>
                <button
                  className="btn-primary !min-h-11"
                  disabled={!ready || save.isPending || campaign?.status === "sending"}
                  onClick={async () => {
                    const count = estimate.data?.reach ?? 0;
                    if (await confirmAction(`Salvar e enviar agora para ${count.toLocaleString("pt-BR")} lead(s)?`)) save.mutate(true);
                  }}
                  type="button"
                >
                  Salvar e enviar <ChevronRight size={16} />
                </button>
              </span>
            )}
          </footer>
        </div>
      </div>
      {campaign && <CampaignStats campaign={campaign} open={stats} onClose={() => setStats(false)} />}
    </div>,
    document.body,
  );
}

function Box({ icon, title, aside, children }: { icon: ReactNode; title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className="grid gap-4 rounded-2xl border border-line bg-surface p-4 sm:p-5">
      <div className="flex items-center gap-2">
        <span className="text-accent">{icon}</span>
        <h2 className="flex-1 text-lg font-semibold text-fg">{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

function ToggleBox({
  icon,
  title,
  description,
  checked,
  onChange,
  children,
}: {
  icon: ReactNode;
  title: string;
  description: string;
  checked: boolean;
  onChange: (on: boolean) => void;
  children?: ReactNode;
}) {
  return (
    <section className="grid gap-4 rounded-2xl border border-line bg-surface p-4 sm:p-5">
      <div className="flex items-center gap-3">
        <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-well text-success">{icon}</span>
        <span className="min-w-0 flex-1">
          <span className="block font-medium text-fg">{title}</span>
          <span className="block text-xs text-muted">{description}</span>
        </span>
        <Switch checked={checked} label={title} onChange={onChange} />
      </div>
      {checked && children}
    </section>
  );
}

function ReviewCard({ icon, label, title, detail, onEdit }: { icon: ReactNode; label: string; title: string; detail: string; onEdit: () => void }) {
  return (
    <div className="flex items-start gap-3 rounded-2xl border border-line bg-surface p-4">
      <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-well text-fg-2">{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="block text-[10px] font-semibold uppercase tracking-[0.18em] text-muted">{label}</span>
        <span className="block truncate font-medium text-fg">{title}</span>
        <span className="block truncate text-xs text-muted">{detail}</span>
      </span>
      <button className="text-xs font-medium text-accent" onClick={onEdit} type="button">
        Editar
      </button>
    </div>
  );
}
