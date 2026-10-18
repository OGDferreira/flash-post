import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, CircleDollarSign, Crown, EyeOff, Lock, QrCode, Trophy, UserPlus, Activity } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { Avatar } from "@/components/Avatar";
import { isPeriodReady, periodParams, type MetricsPeriod } from "@/features/analytics/period";
import { brl, useGoals } from "@/features/wallet/api";
import { apiRequest } from "@/services/api";

type RankingMember = {
  position: number;
  name: string;
  nickname: string;
  avatar_url: string | null;
  is_chief: boolean;
  is_me: boolean;
  has_sales: boolean;
};

type ActivityItem = { kind: "lead" | "pix" | "sale"; lead: string; bot: string; amount: number | null; at: string };

function PanelHeader({ icon, title, subtitle, children }: { icon: ReactNode; title: string; subtitle: string; children?: ReactNode }) {
  return (
    <div className="mb-3 flex items-center justify-between gap-2">
      <div className="flex min-w-0 items-center gap-2">
        <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-surface-inset text-accent">{icon}</span>
        <div className="min-w-0">
          <h3 className="truncate text-sm font-semibold text-fg">{title}</h3>
          <p className="truncate text-[10px] uppercase tracking-[0.14em] text-muted">{subtitle}</p>
        </div>
      </div>
      {children}
    </div>
  );
}

// ------------------------------------------------------------------ activity log

const activityLook = {
  lead: { title: "Novo lead", Icon: UserPlus, tone: "bg-brand-soft text-accent" },
  pix: { title: "Pix gerado", Icon: QrCode, tone: "bg-warning-soft text-warning" },
  sale: { title: "Venda aprovada", Icon: CircleDollarSign, tone: "bg-success-soft text-success" },
} as const;

function ago(iso: string, now: number) {
  const minutes = Math.max(0, Math.floor((now - new Date(iso).getTime()) / 60_000));
  if (minutes < 1) return "agora";
  if (minutes < 60) return `${minutes}min`;
  if (minutes < 1440) return `${Math.floor(minutes / 60)}h`;
  return `${Math.floor(minutes / 1440)}d`;
}

const stamp = (iso: string) =>
  new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", timeZone: "America/Sao_Paulo" });

/** Real-time log of the operation: new leads, Pix generated and approved sales. */
export function ActivityLog() {
  const activity = useQuery({
    queryKey: ["bots", "activity"],
    queryFn: () => apiRequest<{ items: ActivityItem[] }>("/api/bots/activity?limit=40"),
    refetchInterval: 15_000,
    staleTime: 10_000,
  });
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 30_000);
    return () => window.clearInterval(timer);
  }, []);
  const items = activity.data?.items ?? [];
  return (
    <section className="dashboard-card flex flex-col rounded-2xl p-4">
      <PanelHeader icon={<Activity size={16} />} subtitle="Tempo real" title="Log de leads" />
      <div className="max-h-[300px] flex-1 space-y-2 overflow-y-auto pr-1">
        {activity.isLoading ? (
          [0, 1, 2, 3].map((key) => <div className="skeleton h-12" key={key} />)
        ) : items.length === 0 ? (
          <p className="rounded-xl bg-surface-inset px-3 py-6 text-center text-xs text-muted">
            Quando um lead der /start no seu robô, ele aparece aqui na hora.
          </p>
        ) : (
          items.map((item, index) => {
            const look = activityLook[item.kind];
            const detail =
              item.kind === "lead"
                ? "iniciou conversa"
                : item.kind === "pix"
                  ? `gerou Pix de ${brl(item.amount ?? 0)}`
                  : `pagou ${brl(item.amount ?? 0)}`;
            return (
              <div className="flex items-center gap-3 rounded-xl border border-line-soft bg-surface-inset px-3 py-2" key={`${item.kind}-${item.at}-${index}`}>
                <span className={`grid size-8 shrink-0 place-items-center rounded-lg ${look.tone}`}><look.Icon size={15} /></span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-xs font-semibold text-fg">{look.title}</span>
                  <span className="block truncate text-[11px] text-muted">{item.lead} · {detail}</span>
                </span>
                <span className="shrink-0 text-right">
                  <span className="block text-[11px] font-semibold text-fg">{ago(item.at, now)}</span>
                  <span className="block text-[10px] text-muted">{stamp(item.at)}</span>
                </span>
              </div>
            );
          })
        )}
      </div>
    </section>
  );
}

// ------------------------------------------------------------------ awards

/** The user's next FlashBot award, with the banners; arrows browse the other goals.
 * Every award stays locked (grey) until its revenue goal is reached. */
export function NextAward() {
  const goals = useGoals();
  const data = goals.data && goals.data.available ? goals.data : null;
  const list = data?.goals ?? [];
  const currentIndex = Math.max(0, list.findIndex((goal) => goal.current));
  const [index, setIndex] = useState<number | null>(null);
  const shown = index ?? currentIndex;
  const goal = list[shown];
  return (
    <section className="dashboard-card flex flex-col rounded-2xl p-4">
      <PanelHeader icon={<Trophy size={16} />} subtitle="Conquiste novas placas" title="Premiações">
        {list.length > 1 && (
          <div className="flex gap-1">
            <button aria-label="Premiação anterior" className="grid size-7 place-items-center rounded-full bg-surface-inset text-muted disabled:opacity-30" disabled={shown === 0} onClick={() => setIndex(shown - 1)} type="button"><ChevronLeft size={15} /></button>
            <button aria-label="Próxima premiação" className="grid size-7 place-items-center rounded-full bg-surface-inset text-muted disabled:opacity-30" disabled={shown === list.length - 1} onClick={() => setIndex(shown + 1)} type="button"><ChevronRight size={15} /></button>
          </div>
        )}
      </PanelHeader>
      {!data || !goal ? (
        goals.isLoading ? <div className="skeleton mx-auto h-[300px] w-[220px]" /> : (
          <p className="rounded-xl bg-surface-inset px-3 py-6 text-center text-xs text-muted">As premiações aparecem quando sua operação começar a faturar.</p>
        )
      ) : (
        <div className="relative flex flex-1 items-center justify-center py-1">
          {[shown - 1, shown + 1].map((side) => {
            const neighbour = list[side];
            if (!neighbour?.image_url) return null;
            return (
              <img
                alt=""
                aria-hidden="true"
                className={`absolute top-1/2 hidden h-[78%] -translate-y-1/2 rounded-xl object-cover opacity-25 sm:block ${neighbour.reached ? "" : "grayscale"} ${side < shown ? "left-0 -rotate-3" : "right-0 rotate-3"}`}
                key={side}
                src={neighbour.image_url}
              />
            );
          })}
          <article className={`group relative z-10 w-[220px] overflow-hidden rounded-2xl border ${goal.reached ? "border-success/60" : goal.current ? "border-accent/60" : "border-line-soft"}`}>
            <div className="relative aspect-[4/5] overflow-hidden bg-well">
              {goal.image_url ? (
                <img
                  alt={`Premiação de ${brl(goal.amount)} faturados: ${goal.prize}`}
                  className={`h-full w-full object-cover transition duration-500 ${goal.reached ? "" : "brightness-[.4] grayscale group-hover:scale-105 group-hover:brightness-[.6]"}`}
                  src={goal.image_url}
                />
              ) : (
                <div className="grid h-full place-items-center"><Trophy className="text-warning" size={56} /></div>
              )}
              {!goal.reached && (
                <span className="absolute inset-0 grid place-items-center">
                  <span className="rounded-full bg-black/60 p-3 text-white transition duration-500 group-hover:scale-110"><Lock size={20} /></span>
                </span>
              )}
              <span className={`absolute left-2 top-2 rounded-md px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white ${goal.reached ? "bg-success" : goal.current ? "bg-accent" : "bg-black/60"}`}>
                {goal.reached ? "Conquistada" : goal.current ? "★ Próxima" : "Bloqueada"}
              </span>
            </div>
            <div className="space-y-1.5 bg-surface-inset p-3">
              <p className="truncate text-sm font-bold text-fg">{brl(goal.amount)} faturados</p>
              <p className="truncate text-[11px] text-muted">{goal.prize}</p>
              <p className="flex justify-between text-[10px] text-muted">
                <span className="font-semibold uppercase text-accent">Meta</span>
                <span className="font-semibold text-fg">{brl(Math.min(data.month_revenue, goal.amount))} / {brl(goal.amount)}</span>
              </p>
              <div className="h-1.5 overflow-hidden rounded-full bg-well">
                <div className={`h-full rounded-full ${goal.reached ? "bg-success" : "bg-accent"}`} style={{ width: `${Math.min(100, (100 * data.month_revenue) / goal.amount)}%` }} />
              </div>
            </div>
          </article>
        </div>
      )}
    </section>
  );
}

// ------------------------------------------------------------------ ranking

function usePartnersRanking(period: MetricsPeriod) {
  return useQuery({
    queryKey: ["bots", "partners-ranking", periodParams(period)],
    queryFn: () =>
      apiRequest<{ period_label: string; members: RankingMember[] }>(
        `/api/bots/partners-ranking?${new URLSearchParams(periodParams(period))}`,
      ),
    enabled: isPeriodReady(period),
    placeholderData: (previous) => previous,
    staleTime: 30_000,
  });
}

const podium = [
  "border-warning/50 text-warning",
  "border-[#c0c7d4]/50 text-[#c0c7d4]",
  "border-[#d08a4a]/50 text-[#d08a4a]",
];

/** SharkBot-style list. Positions only: the API never sends how much each partner billed. */
export function PartnersRanking({ period }: { period: MetricsPeriod }) {
  const ranking = usePartnersRanking(period);
  const members = ranking.data?.members ?? [];
  return (
    <section className="dashboard-card flex flex-col rounded-2xl p-4">
      <PanelHeader icon={<Crown size={16} />} subtitle="Corrida de faturamento" title="Ranking dos sócios">
        <span className="flex items-center gap-1 rounded-full bg-surface-inset px-2 py-1 text-[10px] text-muted" title="Os valores faturados ficam ocultos">
          <EyeOff size={12} /> Valores ocultos
        </span>
      </PanelHeader>
      <div className="max-h-[300px] flex-1 space-y-2 overflow-y-auto pr-1">
        {ranking.isLoading ? (
          [0, 1, 2, 3].map((key) => <div className="skeleton h-14" key={key} />)
        ) : members.length <= 1 ? (
          <p className="rounded-xl bg-surface-inset px-3 py-6 text-center text-xs text-muted">
            Quando você tiver sócios, a posição de cada um aparece aqui (sem mostrar quanto cada um faturou).
          </p>
        ) : (
          members.map((member) => {
            const top = podium[member.position - 1];
            return (
              <div
                className={`flex items-center gap-3 rounded-xl border px-3 py-2.5 ${member.is_me ? "border-accent/60 bg-brand-soft/40" : "border-line-soft bg-surface-inset"}`}
                key={`${member.position}-${member.nickname}`}
              >
                <span className={`grid size-9 shrink-0 place-items-center rounded-full border-2 ${top ?? "border-line-soft text-muted"}`}>
                  <Avatar className="size-7" name={member.name || member.nickname} src={member.avatar_url} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-1.5">
                    <span className={`truncate text-sm font-semibold ${member.position === 1 ? "text-warning" : "text-fg"}`}>@{member.nickname}</span>
                    <span className={`shrink-0 rounded px-1 text-[10px] font-bold ${member.position === 1 ? "bg-warning text-black" : "bg-well text-muted"}`}>#{member.position}</span>
                  </span>
                  <span className="mt-0.5 inline-block rounded bg-brand-soft px-1.5 text-[9px] font-bold uppercase tracking-wider text-accent">
                    {member.is_me ? "Você" : member.is_chief ? "Dono da operação" : "Sócio"}
                  </span>
                  {!member.has_sales && <span className="ml-1.5 text-[10px] text-muted">sem vendas</span>}
                </span>
                <span className={`flex shrink-0 items-center gap-1 rounded-md border px-2 py-1 text-[10px] font-bold ${top ?? "border-line-soft text-muted"}`}>
                  {member.position <= 3 && <Crown size={11} />}
                  <Lock size={10} /> ••••
                </span>
              </div>
            );
          })
        )}
      </div>
    </section>
  );
}
