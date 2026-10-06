import { useQuery } from "@tanstack/react-query";
import {
  BarChart3,
  CalendarCheck2,
  CircleDollarSign,
  Flame,
  Medal,
  Target,
  TrendingUp,
  UsersRound,
  type LucideIcon,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ErrorState, LoadingState } from "@/components/PageState";
import { apiRequest, type CollaboratorDashboard } from "@/services/api";

function money(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "R$ —";
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(value);
}

function progressMessage(progress: number, goal: number) {
  if (!goal) return "Peça ao administrador para definir sua meta diária.";
  if (progress >= 100) return "Meta diária concluída! Excelente trabalho.";
  if (progress >= 70) return "Está quase lá — mantenha o ritmo!";
  if (progress >= 35) return "Bom progresso. Continue avançando!";
  return "Cada conexão conta. Vamos começar!";
}

function progressValue(value: number | undefined) {
  return Math.min(100, Math.max(0, Number(value) || 0));
}

function brazilDayLabel(dayOffset: number) {
  const today = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Sao_Paulo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
  const [year, month, day] = today.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day - dayOffset));
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    timeZone: "UTC",
  }).format(date);
}

function accountDateLabel(value: string | null) {
  if (!value) return "Data indisponível";
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    timeZone: "America/Sao_Paulo",
  }).format(new Date(value));
}

export function CollaboratorDashboardPage() {
  const dashboard = useQuery({
    queryKey: ["collaborators", "dashboard"],
    queryFn: () => apiRequest<CollaboratorDashboard>("/api/collaborators/dashboard"),
    refetchInterval: 30_000,
    retry: false,
  });
  const ranking = useQuery({
    queryKey: ["collaborators", "ranking"],
    queryFn: () =>
      apiRequest<{
        collaborators: {
          user_id: string;
          nickname: string;
          connections: number;
          position: number;
        }[];
        total_connections: number;
      }>("/api/collaborators/ranking"),
    refetchInterval: 60_000,
    retry: false,
  });

  if (dashboard.isLoading) return <LoadingState label="Carregando seu painel" />;
  if (dashboard.error || !dashboard.data) {
    return <ErrorState message="Não foi possível carregar seu painel de produção." />;
  }

  const data = dashboard.data;
  const recentDays = Array.isArray(data.recent_days)
    ? data.recent_days.map((count) => Number(count) || 0)
    : [];
  const ratePerConnection = Number(data.rate_per_connection) || 0;
  const recentEarnings = Array.isArray(data.recent_earnings)
    ? data.recent_earnings.map((amount) => Number(amount) || 0)
    : recentDays.map((count) => count * ratePerConnection);
  const recentPayments = Array.isArray(data.recent_payments)
    ? data.recent_payments.map((amount) => Number(amount) || 0)
    : recentDays.map(() => 0);
  const weeklyConnections = recentDays.reduce((total, count) => total + count, 0);
  const rankedCollaborators = Array.isArray(ranking.data?.collaborators)
    ? ranking.data.collaborators
    : [];
  const totalRankedConnections =
    Number(ranking.data?.total_connections) ||
    rankedCollaborators.reduce((total, person) => total + (Number(person.connections) || 0), 0);
  const productionByDay = recentDays.map((connections, dayOffset) => ({
    day: brazilDayLabel(6 - dayOffset),
    connections,
  }));
  const moneyByDay = recentDays.map((_, dayOffset) => ({
    day: brazilDayLabel(6 - dayOffset),
    aReceber: Number(recentEarnings[dayOffset] ?? 0),
    recebido: Number(recentPayments[dayOffset] ?? 0),
  }));

  return (
    <div className="w-full space-y-3 xl:grid xl:h-[calc(100dvh-216px)] xl:min-h-[620px] xl:grid-rows-[auto_auto_minmax(0,1fr)] xl:gap-3 xl:space-y-0">
      <header className="flex items-center gap-3">
        {data.avatar_url ? (
          <img
            alt=""
            className="size-10 rounded-full border border-[#34446f] object-cover"
            src={data.avatar_url}
          />
        ) : (
          <span className="grid size-10 place-items-center rounded-full bg-[#171e31] text-sm font-semibold text-[#aab7ff]">
            {(data.full_name || data.nickname || "C").slice(0, 1).toUpperCase()}
          </span>
        )}
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-[#8295ff]">
            Seu painel de produção
          </p>
          <h1 className="mt-0.5 text-lg font-semibold text-[#f5f7fb]">
            Olá, {data.nickname || data.full_name || "colaborador"}
          </h1>
        </div>
      </header>

      <section aria-label="Resumo de produção e pagamentos" className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        <Metric icon={UsersRound} label="Conexões hoje" value={String(data.connections_today ?? 0)} />
        <Metric icon={CalendarCheck2} label="Conexões na semana" value={String(weeklyConnections)} />
        <Metric icon={BarChart3} label="Conexões no mês" value={String(data.connections_month ?? 0)} />
        <Metric icon={CircleDollarSign} label="A receber no mês" value={money(data.due_month)} />
        <Metric icon={CircleDollarSign} label="Recebido no mês" value={money(data.paid_month)} />
        <Metric icon={TrendingUp} label="Total do mês" value={money(data.earnings_month)} />
        <Metric icon={Flame} label="Pode alcançar no mês" value={money(data.projected_month)} />
      </section>

      <section className="grid min-h-0 gap-3 xl:grid-cols-[minmax(0,1.8fr)_minmax(280px,1fr)]">
        <div className="grid min-h-0 gap-3 xl:grid-rows-[auto_minmax(0,1fr)]">
          <section className="grid gap-3 sm:grid-cols-2">
            <article className="dashboard-card space-y-2 rounded-xl p-3">
              <div className="flex items-center gap-2">
                <Target className="text-[#8295ff]" size={16} />
                <h2 className="text-xs font-semibold text-[#eef1f8]">Meta diária</h2>
              </div>
              <div className="flex items-end justify-between gap-2">
                <p className="text-2xl font-semibold text-[#f5f7fb]">
                  {data.connections_today ?? 0}
                  <span className="text-sm font-normal text-[#78839b]">
                    {" "}/ {data.daily_connection_goal || "—"}
                  </span>
                </p>
                <p className="text-sm font-semibold text-[#aab7ff]">
                  {progressValue(data.daily_progress)}%
                </p>
              </div>
              <ProgressBar value={progressValue(data.daily_progress)} />
              <p className="text-[11px] text-[#94a3b8]">
                {progressMessage(progressValue(data.daily_progress), data.daily_connection_goal)}
              </p>
            </article>

            <article className="dashboard-card space-y-2 rounded-xl p-3">
              <div className="flex items-center gap-2">
                <Flame className="text-[#f2d48a]" size={16} />
                <h2 className="text-xs font-semibold text-[#eef1f8]">Meta mensal</h2>
              </div>
              <div className="flex items-end justify-between gap-2">
                <p className="text-2xl font-semibold text-[#f5f7fb]">
                  {data.connections_month ?? 0}
                  <span className="text-sm font-normal text-[#78839b]">
                    {" "}/ {data.monthly_connection_goal || "—"}
                  </span>
                </p>
                <p className="text-sm font-semibold text-[#f2d48a]">
                  {progressValue(data.monthly_progress)}%
                </p>
              </div>
              <ProgressBar value={progressValue(data.monthly_progress)} color="gold" />
              <div className="flex justify-between gap-2 text-[11px] text-[#94a3b8]">
                <span>A receber: {money(data.due_month)}</span>
                <span>Bónus: {money(data.monthly_bonus)}</span>
              </div>
            </article>
          </section>

          <section className="grid gap-3 xl:min-h-0 xl:grid-cols-2">
            <article className="dashboard-card flex min-h-[300px] min-w-0 flex-col rounded-xl p-3 xl:min-h-0">
              <header className="dashboard-panel-header">
                <div className="flex items-center gap-2">
                  <BarChart3 className="shrink-0 text-[#8295ff]" size={16} />
                  <h2 className="dashboard-panel-title mt-0">Contas conectadas por dia</h2>
                </div>
                <span className="shrink-0 text-[10px] text-[#78839b]">7 dias</span>
              </header>
              <div className="mt-2 min-h-[250px] w-full flex-1 xl:min-h-0">
                <ResponsiveContainer height="100%" width="100%">
                  <BarChart data={productionByDay} margin={{ top: 8, right: 4, left: -20, bottom: 0 }}>
                    <CartesianGrid stroke="#232a3b" strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="day" stroke="#78839b" tick={{ fontSize: 10 }} />
                    <YAxis allowDecimals={false} stroke="#78839b" tick={{ fontSize: 10 }} />
                    <Tooltip
                      contentStyle={{
                        background: "#10141b",
                        border: "1px solid #303954",
                        borderRadius: 8,
                        color: "#f5f7fb",
                      }}
                    />
                    <Bar dataKey="connections" fill="#8295ff" name="Contas conectadas" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <p className="mt-1 text-[10px] text-[#78839b]">
                Valor por conexão: {money(ratePerConnection)}
              </p>
            </article>

            <article className="dashboard-card flex min-h-[300px] min-w-0 flex-col rounded-xl p-3 xl:min-h-0">
              <header className="dashboard-panel-header">
                <div className="flex items-center gap-2">
                  <CircleDollarSign className="shrink-0 text-[#76c8a0]" size={16} />
                  <h2 className="dashboard-panel-title mt-0">A receber e pagos por dia</h2>
                </div>
                <span className="shrink-0 text-[10px] text-[#78839b]">7 dias</span>
              </header>
              <div className="mt-2 min-h-[250px] w-full flex-1 xl:min-h-0">
                <ResponsiveContainer height="100%" width="100%">
                  <BarChart data={moneyByDay} margin={{ top: 8, right: 4, left: -18, bottom: 0 }}>
                    <CartesianGrid stroke="#232a3b" strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="day" stroke="#78839b" tick={{ fontSize: 10 }} />
                    <YAxis
                      stroke="#78839b"
                      tick={{ fontSize: 9 }}
                      tickFormatter={(value: number) => `R$${value}`}
                    />
                    <Tooltip
                      formatter={(value) => [money(Number(value)), ""]}
                      contentStyle={{
                        background: "#10141b",
                        border: "1px solid #303954",
                        borderRadius: 8,
                        color: "#f5f7fb",
                      }}
                    />
                    <Legend wrapperStyle={{ fontSize: 10 }} />
                    <Bar dataKey="aReceber" fill="#8295ff" name="A receber" radius={[3, 3, 0, 0]} />
                    <Bar dataKey="recebido" fill="#76c8a0" name="Recebido" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </article>
          </section>
        </div>

        <section aria-label="Ranking mensal de produção" className="dashboard-card flex min-h-0 flex-col rounded-xl p-3">
          <header className="mb-2 flex items-center gap-2">
            <Medal className="shrink-0 text-[#f2d48a]" size={17} />
            <h2 className="text-sm font-semibold text-[#eef1f8]">
              Ranking de produção
            </h2>
          </header>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {ranking.isLoading ? (
              <p className="text-sm text-[#94a3b8]">Carregando ranking...</p>
            ) : ranking.error ? (
              <p className="text-sm text-[#f1a3ad]">Não foi possível carregar o ranking.</p>
            ) : rankedCollaborators.length ? (
              <table className="w-full text-left text-xs">
                <thead className="text-[10px] uppercase text-[#78839b]">
                  <tr>
                    <th className="py-1.5 pr-2 font-medium">#</th>
                    <th className="py-1.5 pr-2 font-medium">Colaborador</th>
                    <th className="py-1.5 text-right font-medium">Contas</th>
                  </tr>
                </thead>
                <tbody>
                  {rankedCollaborators.slice(0, 6).map((person) => (
                    <tr className="border-t border-[#202838]" key={person.user_id}>
                      <td className="py-2 pr-2 font-semibold text-[#f2d48a]">{person.position}</td>
                      <td className="max-w-0 truncate py-2 pr-2 text-[#e6eaf2]">
                        @{person.nickname}
                      </td>
                      <td className="py-2 text-right font-semibold text-[#f5f7fb]">
                        {person.connections}
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t border-[#34446f] text-[#cbd5e1]">
                    <th className="py-2 pr-2" colSpan={2}>Total da equipe</th>
                    <td className="py-2 text-right font-semibold">
                      {totalRankedConnections}
                    </td>
                  </tr>
                </tfoot>
              </table>
            ) : (
              <p className="text-sm text-[#94a3b8]">Ainda não há produção neste mês.</p>
            )}

          </div>
        </section>
      </section>

      <section aria-label="Valores das minhas contas" className="dashboard-card rounded-xl p-4">
        <h2 className="mb-3 text-sm font-semibold text-[#eef1f8]">
          Valores das minhas contas
        </h2>
        {Array.isArray(data.account_earnings) && data.account_earnings.length ? (
          <ul className="grid gap-x-6 sm:grid-cols-2 lg:grid-cols-3">
            {data.account_earnings.map((account) => (
              <li
                className="flex items-center justify-between gap-2 border-t border-[#202838] py-2 text-xs"
                key={account.account_id}
              >
                <span className="min-w-0 truncate text-[#e6eaf2]">
                  @{account.username}
                  <span className="ml-2 text-[10px] text-[#78839b]">
                    {accountDateLabel(account.connected_at)}
                  </span>
                </span>
                <strong className="shrink-0 font-medium text-[#f2d48a]">
                  {money(account.rate_per_connection)}
                </strong>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-[#78839b]">
            Os valores aparecerão quando suas contas forem conectadas.
          </p>
        )}
      </section>
    </div>
  );
}

function Metric({
  icon: Icon,
  label,
  value,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
}) {
  return (
    <article className="dashboard-card rounded-lg px-3 py-2">
      <div className="flex min-w-0 items-center gap-2">
        <Icon className="shrink-0 text-[#8295ff]" size={14} />
        <p className="truncate text-[11px] text-[#94a3b8]">{label}</p>
      </div>
      <p className="mt-1 text-lg font-semibold leading-tight text-[#f5f7fb]">{value}</p>
    </article>
  );
}

function ProgressBar({ value, color = "blue" }: { value: number; color?: "blue" | "gold" }) {
  return (
    <div
      aria-label={`Progresso ${value}%`}
      aria-valuemax={100}
      aria-valuemin={0}
      aria-valuenow={value}
      className="h-2 overflow-hidden rounded-full bg-[#252c3e]"
      role="progressbar"
    >
      <div
        className={`h-full rounded-full transition-[width] duration-500 ${
          color === "gold"
            ? "bg-gradient-to-r from-[#d69b44] to-[#f2d48a]"
            : "bg-gradient-to-r from-[#536dfe] to-[#b171ff]"
        }`}
        style={{ width: `${value}%` }}
      />
    </div>
  );
}
