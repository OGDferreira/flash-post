import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clock, Eye, Handshake, Pause, Play, Plus, RotateCcw, Trash2, UserPlus } from "lucide-react";

import { apiRequest, ApiError } from "@/services/api";
import type { Bot } from "../types";
import { botPartners, invitePartner, ownerFinance, removePartnership, resendInvite, SPLIT_KIND_LABEL, updatePartnership, type AccessLevel, type Partnership, type SplitKind } from "./api";

const ACCESS_LABEL: Record<AccessLevel, string> = { operational: "Operacional", read_only: "Somente leitura" };
const SPLIT_KINDS: SplitKind[] = ["plan", "upsell", "downsell", "remarketing"];

function SplitByKindEditor({ part, onChanged }: { part: Partnership; onChanged: () => void }) {
  const [open, setOpen] = useState(false);
  const current = part.split_by_kind ?? {};
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(SPLIT_KINDS.map((k) => [k, current[k] != null ? String(current[k]) : ""])),
  );
  const save = useMutation({
    mutationFn: () => {
      const body: Partial<Record<SplitKind, number | null>> = {};
      for (const k of SPLIT_KINDS) {
        const raw = (values[k] ?? "").replace(",", ".").trim();
        body[k] = raw === "" ? null : Number(raw);
      }
      return updatePartnership(part.id, { split_by_kind: body });
    },
    onSuccess: onChanged,
  });
  const hasAny = SPLIT_KINDS.some((k) => current[k] != null);

  return (
    <div className="mt-3 rounded-xl border border-line bg-well/60 p-3">
      <button className="flex w-full items-center justify-between text-left text-xs font-medium text-fg-2" onClick={() => setOpen((o) => !o)} type="button">
        <span>Split por plano {hasAny ? "(personalizado)" : "(usa a % geral)"}</span>
        <span className="text-muted">{open ? "−" : "+"}</span>
      </button>
      {open && (
        <>
          <p className="mt-1 text-[11px] text-muted">Deixe em branco para usar a % geral ({Number(part.partner_percent)}%) naquele tipo de oferta.</p>
          <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
            {SPLIT_KINDS.map((k) => (
              <label key={k} className="text-[11px] text-muted">
                {SPLIT_KIND_LABEL[k]}
                <input
                  className="field !min-h-9 !text-sm"
                  inputMode="decimal"
                  placeholder={`${Number(part.partner_percent)}%`}
                  value={values[k] ?? ""}
                  onChange={(e) => setValues((v) => ({ ...v, [k]: e.target.value }))}
                />
              </label>
            ))}
          </div>
          <button className="btn-secondary !min-h-8 mt-2 !text-xs" disabled={save.isPending} onClick={() => save.mutate()} type="button">
            Salvar split por plano
          </button>
          {save.error && <p className="mt-1 text-xs text-danger">{save.error instanceof ApiError ? save.error.message : "Não foi possível salvar."}</p>}
        </>
      )}
    </div>
  );
}
import { PartnerFinanceCard } from "./PartnerFinanceCard";

const STATUS_LABEL: Record<Partnership["status"], string> = {
  PENDING: "Convite enviado", ACTIVE: "Ativo", PAUSED: "Pausado", DECLINED: "Recusado", REVOKED: "Removido",
};

function PartnerRow({ part, canZeroFee, onChanged }: { part: Partnership; canZeroFee: boolean; onChanged: () => void }) {
  const [percent, setPercent] = useState(String(part.partner_percent));
  const [fee, setFee] = useState(String(part.bot_fee));
  const save = useMutation({
    mutationFn: (body: Parameters<typeof updatePartnership>[1]) => updatePartnership(part.id, body),
    onSuccess: onChanged,
  });
  const remove = useMutation({ mutationFn: () => removePartnership(part.id), onSuccess: onChanged });
  const resend = useMutation({ mutationFn: () => resendInvite(part.id), onSuccess: onChanged });
  const name = part.partner?.name || part.partner?.email || "Parceiro";
  const isExpired = Boolean(part.expired);
  const pendingInfo = part.status === "PENDING" && !part.accepted_at && part.invite_expires_at && !isExpired
    ? `Convite expira em ${new Date(part.invite_expires_at).toLocaleDateString("pt-BR")}`
    : null;

  return (
    <div className="rounded-2xl border border-line bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate font-semibold text-fg">{name}</p>
          <p className="truncate text-xs text-muted">{part.partner?.username ? `@${part.partner.username}` : part.partner?.email}</p>
        </div>
        <div className="flex items-center gap-1.5">
          {part.access_level === "read_only" && (
            <span className="flex items-center gap-1 rounded-full bg-well px-2 py-1 text-[11px] font-medium text-fg-2"><Eye size={12} /> {ACCESS_LABEL.read_only}</span>
          )}
          {isExpired ? (
            <span className="flex items-center gap-1 rounded-full bg-danger/15 px-2.5 py-1 text-[11px] font-medium text-danger"><Clock size={12} /> Expirado</span>
          ) : (
            <span className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${part.status === "ACTIVE" ? "bg-success-soft text-success" : part.status === "PAUSED" ? "bg-warning/15 text-warning" : "bg-well text-fg-2"}`}>
              {STATUS_LABEL[part.status]}
            </span>
          )}
        </div>
      </div>
      {pendingInfo && <p className="mt-1 flex items-center gap-1 text-[11px] text-muted"><Clock size={11} /> {pendingInfo}</p>}
      <div className="mt-3 flex flex-wrap items-end gap-2">
        <label className="text-xs text-muted">
          % do parceiro
          <input className="field !min-h-9 !w-24 !text-sm" inputMode="decimal" value={percent} onChange={(e) => setPercent(e.target.value)} />
        </label>
        <label className="text-xs text-muted">
          Taxa do bot (R$/venda)
          <input className="field !min-h-9 !w-28 !text-sm disabled:opacity-60" disabled={!canZeroFee} inputMode="decimal" value={fee} onChange={(e) => setFee(e.target.value)} title={canZeroFee ? "" : "Só o super admin altera a taxa do bot."} />
        </label>
        <label className="text-xs text-muted">
          Acesso
          <select
            className="field !min-h-9 !w-auto !text-sm"
            value={part.access_level}
            disabled={save.isPending}
            onChange={(e) => save.mutate({ access_level: e.target.value as AccessLevel })}
          >
            <option value="operational">Operacional</option>
            <option value="read_only">Somente leitura</option>
          </select>
        </label>
        <button
          className="btn-secondary !min-h-9"
          disabled={save.isPending}
          onClick={() => save.mutate({ partner_percent: percent.replace(",", "."), ...(canZeroFee ? { bot_fee: fee.replace(",", ".") } : {}) })}
          type="button"
        >
          Salvar
        </button>
        {part.status === "ACTIVE" ? (
          <button className="btn-secondary !min-h-9" disabled={save.isPending} onClick={() => save.mutate({ status: "PAUSED" })} type="button">
            <Pause size={15} /> Pausar
          </button>
        ) : (part.status === "PAUSED" || (part.status === "PENDING" && part.accepted_at)) ? (
          <button className="btn-secondary !min-h-9" disabled={save.isPending} onClick={() => save.mutate({ status: "ACTIVE" })} type="button">
            <Play size={15} /> Ativar
          </button>
        ) : null}
        {(isExpired || (part.status === "PENDING" && !part.accepted_at)) && (
          <button className="btn-secondary !min-h-9" disabled={resend.isPending} onClick={() => resend.mutate()} type="button">
            <RotateCcw size={15} /> Reenviar
          </button>
        )}
        <button className="btn-secondary !min-h-9 !text-danger" disabled={remove.isPending} onClick={() => remove.mutate()} type="button">
          <Trash2 size={15} /> Remover
        </button>
      </div>
      {(save.error || remove.error) && (
        <p className="mt-2 text-sm text-danger">
          {(save.error || remove.error) instanceof ApiError ? (save.error || remove.error)!.message : "Não foi possível salvar."}
        </p>
      )}
      <SplitByKindEditor part={part} onChanged={onChanged} />
    </div>
  );
}

function InviteForm({ botId, onInvited, canZeroFee, defaultFee }: { botId: string; onInvited: () => void; canZeroFee: boolean; defaultFee: number }) {
  const [identifier, setIdentifier] = useState("");
  const [percent, setPercent] = useState("50");
  const [fee, setFee] = useState(String(defaultFee));
  const [access, setAccess] = useState<AccessLevel>("operational");
  const [expiryDays, setExpiryDays] = useState(7);
  const invite = useMutation({
    mutationFn: () => invitePartner(botId, { identifier: identifier.trim(), partner_percent: percent.replace(",", "."), access_level: access, invite_expiry_days: expiryDays, ...(canZeroFee ? { bot_fee: fee.replace(",", ".") } : {}) }),
    onSuccess: () => { setIdentifier(""); onInvited(); },
  });
  return (
    <form className="rounded-2xl border border-dashed border-line bg-well p-4" onSubmit={(e) => { e.preventDefault(); if (identifier.trim()) invite.mutate(); }}>
      <p className="flex items-center gap-2 text-sm font-semibold text-fg"><UserPlus size={16} /> Convidar parceiro</p>
      <p className="mt-0.5 text-xs text-muted">E-mail, @usuário ou apelido de um usuário já cadastrado na Flash.</p>
      <div className="mt-3 flex flex-wrap items-end gap-2">
        <label className="min-w-[12rem] flex-1 text-xs text-muted">
          Usuário
          <input className="field !min-h-9 !text-sm" placeholder="augusto@exemplo.com" value={identifier} onChange={(e) => setIdentifier(e.target.value)} />
        </label>
        <label className="text-xs text-muted">
          % do parceiro
          <input className="field !min-h-9 !w-24 !text-sm" inputMode="decimal" value={percent} onChange={(e) => setPercent(e.target.value)} />
        </label>
        <label className="text-xs text-muted">
          Acesso
          <select className="field !min-h-9 !w-auto !text-sm" value={access} onChange={(e) => setAccess(e.target.value as AccessLevel)}>
            <option value="operational">Operacional (edita funil)</option>
            <option value="read_only">Somente leitura</option>
          </select>
        </label>
        <label className="text-xs text-muted">
          Convite válido por
          <select className="field !min-h-9 !w-auto !text-sm" value={expiryDays} onChange={(e) => setExpiryDays(Number(e.target.value))}>
            <option value={1}>1 dia</option>
            <option value={3}>3 dias</option>
            <option value={7}>7 dias</option>
            <option value={30}>30 dias</option>
          </select>
        </label>
        {canZeroFee && (
          <label className="text-xs text-muted">
            Taxa do bot (R$)
            <input className="field !min-h-9 !w-24 !text-sm" inputMode="decimal" value={fee} onChange={(e) => setFee(e.target.value)} />
          </label>
        )}
        <button className="btn-primary !min-h-9" disabled={invite.isPending || !identifier.trim()} type="submit">
          <Plus size={15} /> Enviar convite
        </button>
      </div>
      {invite.error && <p className="mt-2 text-sm text-danger">{invite.error instanceof ApiError ? invite.error.message : "Não foi possível convidar."}</p>}
    </form>
  );
}

/** Owner view: pick one of your bots and manage its partners, the split and the finance panel. */
export function BotPartnersPanel() {
  const queryClient = useQueryClient();
  const bots = useQuery({ queryKey: ["bots"], queryFn: () => apiRequest<{ bots: Bot[] }>("/api/bots"), retry: false });
  const [botId, setBotId] = useState<string>("");
  useEffect(() => {
    if (!botId && bots.data?.bots?.length) setBotId(bots.data.bots[0].id);
  }, [bots.data, botId]);

  const data = useQuery({ queryKey: ["bot-partners", botId], queryFn: () => botPartners(botId), enabled: Boolean(botId) });
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["bot-partners", botId] });
    void queryClient.invalidateQueries({ queryKey: ["bot-partners", "finance", botId] });
  };

  if (bots.isLoading) return <p className="text-sm text-muted">Carregando bots…</p>;
  if (!bots.data?.bots?.length) {
    return <p className="rounded-xl border border-line bg-surface px-4 py-6 text-center text-sm text-muted">Conecte um bot primeiro para compartilhá-lo com um parceiro.</p>;
  }

  const partners = data.data?.partners ?? [];
  const canZeroFee = data.data?.can_zero_fee ?? false;
  const activePercent = data.data?.active_percent ?? 0;
  const remaining = data.data?.active_percent_remaining ?? 100;
  const activePartners = partners.filter((p) => p.status === "ACTIVE");

  return (
    <div className="space-y-4">
      <div className="dashboard-card flex flex-wrap items-center gap-3 rounded-2xl px-4 py-3">
        <span className="flex items-center gap-2 text-sm font-medium text-fg"><Handshake size={16} /> Bot</span>
        <select className="field !min-h-10 !w-auto !text-sm" value={botId} onChange={(e) => setBotId(e.target.value)}>
          {bots.data.bots.map((bot) => <option key={bot.id} value={bot.id}>{bot.name} (@{bot.username})</option>)}
        </select>
      </div>

      {partners.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-line bg-surface px-4 py-3 text-sm">
          <span className="text-muted">
            Parceiros ativos: <strong className="text-fg">{activePartners.length}</strong> · soma das porcentagens:{" "}
            <strong className={activePercent > 100 ? "text-danger" : "text-fg"}>{activePercent.toFixed(2).replace(".", ",")}%</strong>
          </span>
          <span className="text-muted">Disponível para dividir: <strong className="text-fg">{remaining.toFixed(2).replace(".", ",")}%</strong></span>
        </div>
      )}

      <InviteForm botId={botId} canZeroFee={canZeroFee} defaultFee={data.data?.default_bot_fee ?? 0} onInvited={refresh} />

      <div className="space-y-3">
        {partners.map((part) => <PartnerRow key={part.id} part={part} canZeroFee={canZeroFee} onChanged={refresh} />)}
        {partners.length === 0 && <p className="text-sm text-muted">Nenhum parceiro neste bot ainda.</p>}
      </div>

      {activePartners.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-lg font-semibold text-fg">Financeiro das parcerias</h2>
          {activePartners.map((part) => (
            <div key={part.id} className="space-y-2">
              {activePartners.length > 1 && (
                <p className="text-sm font-medium text-fg-2">
                  {part.partner?.name || part.partner?.email || "Parceiro"} · {Number(part.partner_percent).toFixed(2).replace(".", ",")}%
                </p>
              )}
              <PartnerFinanceCard
                partnershipId={part.id}
                canLogPayout
                queryKey={["bot-partners", "finance", botId, part.id]}
                fetchPanel={(period) => ownerFinance(botId, period, part.id)}
              />
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
