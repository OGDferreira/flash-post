import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, Link2, UserCheck, UserX } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { confirmAction } from "@/lib/confirm";
import { ApiError, apiRequest } from "@/services/api";

export type PendingCollaborator = {
  member_id: string;
  full_name: string;
  nickname: string;
  email: string;
  requested_at: string;
  rate_per_connection: string;
  daily_connection_goal: number;
  monthly_connection_goal: number;
  monthly_bonus: string;
};

type Settings = {
  rate_per_connection: string;
  daily_connection_goal: number;
  monthly_connection_goal: number;
  monthly_bonus: string;
};
type Defaults = Settings & { from_last_invite: boolean };
type Invite = Settings & {
  id: string;
  status: "active" | "expired" | "used" | "revoked";
  uses: number;
  max_uses: number;
  expires_at: string;
  created_at: string;
};
type Created = Invite & { token: string };

const statusLabel: Record<Invite["status"], string> = {
  active: "Ativo",
  expired: "Expirado",
  used: "Usado",
  revoked: "Revogado",
};

function brl(value: string) {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(Number(value) || 0);
}

export function CollaboratorInvitesPanel({ pending }: { pending: PendingCollaborator[] }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState<Settings | null>(null);
  const [days, setDays] = useState(7);
  const [created, setCreated] = useState<Created | null>(null);
  const [copied, setCopied] = useState(false);

  const defaults = useQuery({
    queryKey: ["collaborators", "invite-defaults"],
    queryFn: () => apiRequest<Defaults>("/api/collaborators/invites/defaults"),
    enabled: open,
    retry: false,
  });
  const invites = useQuery({
    queryKey: ["collaborators", "invites"],
    queryFn: () => apiRequest<{ invites: Invite[] }>("/api/collaborators/invites"),
    retry: false,
  });
  const form: Settings | null = values ?? defaults.data ?? null;
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["collaborators"] });

  const create = useMutation({
    mutationFn: () => apiRequest<Created>("/api/collaborators/invites", { method: "POST", body: { ...form, expires_in_days: days } }),
    onSuccess: async (result) => {
      setCreated(result);
      await refresh();
    },
  });
  const revoke = useMutation({
    mutationFn: (id: string) => apiRequest<void>(`/api/collaborators/invites/${id}`, { method: "DELETE" }),
    onSuccess: refresh,
  });
  const approve = useMutation({
    mutationFn: (id: string) => apiRequest<void>(`/api/collaborators/${id}/approve`, { method: "POST" }),
    onSuccess: refresh,
  });
  const reject = useMutation({
    mutationFn: (id: string) => apiRequest<void>(`/api/collaborators/${id}/reject`, { method: "POST" }),
    onSuccess: refresh,
  });

  const close = () => {
    setOpen(false);
    setCreated(null);
    setValues(null);
    setCopied(false);
  };
  const link = created ? `${window.location.origin}/convite/${created.token}` : "";
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };
  const patch = (key: keyof Settings, value: string | number) =>
    setValues({ ...(form as Settings), [key]: value });
  const error = [create, approve, reject, revoke]
    .map((m) => m.error)
    .find(Boolean);
  const activeInvites = (invites.data?.invites ?? []).filter((item) => item.status === "active");

  return (
    <section aria-label="Convites e aprovações" className="dashboard-card space-y-4 rounded-xl p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-fg">Convite por link</h2>
          <p className="mt-1 text-xs text-muted">
            O colaborador abre o link e faz o próprio cadastro. Você define o valor por conta e as metas, e libera o acesso depois.
          </p>
        </div>
        <Button onClick={() => setOpen(true)} variant="primary">
          <Link2 size={16} />
          Gerar link
        </Button>
      </div>

      {error && (
        <p className="rounded-xl border border-danger/30 bg-danger-soft px-3 py-2 text-sm text-danger" role="alert">
          {error instanceof ApiError ? error.message : "Não foi possível concluir a ação."}
        </p>
      )}

      {pending.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-medium uppercase tracking-[0.12em] text-warning">
            Aguardando sua aprovação ({pending.length})
          </h3>
          <ul className="space-y-2">
            {pending.map((item) => (
              <li className="flex flex-wrap items-center gap-3 rounded-xl border border-line bg-surface-inset p-3" key={item.member_id}>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-fg">
                    {item.full_name} <span className="text-xs text-muted">@{item.nickname}</span>
                  </p>
                  <p className="truncate text-xs text-muted">
                    {item.email} · {brl(item.rate_per_connection)} por conta · meta {item.daily_connection_goal}/dia, {item.monthly_connection_goal}/mês
                  </p>
                </div>
                <Button disabled={approve.isPending} onClick={() => approve.mutate(item.member_id)} size="sm" variant="primary">
                  <UserCheck size={15} />
                  Aprovar
                </Button>
                <Button
                  disabled={reject.isPending}
                  onClick={async () => {
                    if (await confirmAction({ title: "Recusar cadastro?", message: `${item.full_name} perde o cadastro e precisa de um novo convite.`, confirmLabel: "Recusar", danger: true })) {
                      reject.mutate(item.member_id);
                    }
                  }}
                  size="sm"
                  variant="danger"
                >
                  <UserX size={15} />
                  Recusar
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {activeInvites.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-medium uppercase tracking-[0.12em] text-muted">Links ativos</h3>
          <ul className="space-y-2">
            {activeInvites.map((item) => (
              <li className="flex flex-wrap items-center gap-3 rounded-xl border border-line bg-surface-inset p-3 text-xs text-muted" key={item.id}>
                <Badge tone="success">{statusLabel[item.status]}</Badge>
                <span className="min-w-0 flex-1">
                  {brl(item.rate_per_connection)} por conta · {item.uses}/{item.max_uses} usos · expira em{" "}
                  {new Date(item.expires_at).toLocaleDateString("pt-BR")}
                </span>
                <Button disabled={revoke.isPending} onClick={() => revoke.mutate(item.id)} size="sm" variant="ghost">
                  Revogar
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <Modal
        description="O valor e as metas ficam salvos no link. A próxima vez, ele já abre com a última configuração usada."
        onClose={close}
        open={open}
        title={created ? "Link gerado" : "Novo link de convite"}
        footer={
          created ? (
            <Button onClick={close} variant="primary">Concluir</Button>
          ) : (
            <>
              <Button onClick={close} variant="ghost">Cancelar</Button>
              <Button disabled={!form || create.isPending} onClick={() => create.mutate()} variant="primary">
                Gerar link
              </Button>
            </>
          )
        }
      >
        {created ? (
          <div className="space-y-3">
            <p className="text-sm text-muted">
              Copie e envie ao colaborador. Por segurança o link aparece só agora; depois dele, gere outro.
            </p>
            <div className="flex gap-2">
              <input aria-label="Link de convite" className="field" onFocus={(e) => e.currentTarget.select()} readOnly value={link} />
              <Button onClick={copy} variant="primary">
                {copied ? <Check size={16} /> : <Copy size={16} />}
                {copied ? "Copiado" : "Copiar"}
              </Button>
            </div>
          </div>
        ) : !form ? (
          <p className="text-sm text-muted">Carregando última configuração…</p>
        ) : (
          <div className="space-y-3">
            {defaults.data?.from_last_invite && !values && (
              <Badge tone="brand">Última configuração usada</Badge>
            )}
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="grid gap-1.5 text-xs text-muted">
                Valor por conta (R$)
                <input className="field" min={0} onChange={(e) => patch("rate_per_connection", e.target.value)} step="0.01" type="number" value={form.rate_per_connection} />
              </label>
              <label className="grid gap-1.5 text-xs text-muted">
                Bônus mensal (R$)
                <input className="field" min={0} onChange={(e) => patch("monthly_bonus", e.target.value)} step="0.01" type="number" value={form.monthly_bonus} />
              </label>
              <label className="grid gap-1.5 text-xs text-muted">
                Meta diária (contas)
                <input className="field" min={0} onChange={(e) => patch("daily_connection_goal", Number(e.target.value))} step={1} type="number" value={form.daily_connection_goal} />
              </label>
              <label className="grid gap-1.5 text-xs text-muted">
                Meta mensal (contas)
                <input className="field" min={0} onChange={(e) => patch("monthly_connection_goal", Number(e.target.value))} step={1} type="number" value={form.monthly_connection_goal} />
              </label>
              <label className="grid gap-1.5 text-xs text-muted">
                Validade do link (dias)
                <input className="field" max={30} min={1} onChange={(e) => setDays(Math.min(30, Math.max(1, Number(e.target.value) || 1)))} step={1} type="number" value={days} />
              </label>
            </div>
            <p className="text-xs text-muted">O link vale para um cadastro e expira no prazo acima.</p>
          </div>
        )}
      </Modal>
    </section>
  );
}
