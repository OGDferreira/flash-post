import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useReducedMotion } from "framer-motion";
import {
  Activity,
  AlertTriangle,
  CircleCheck,
  Clock3,
  Eye,
  UsersRound,
  Wallet,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ErrorState, LoadingState } from "@/components/PageState";
import { useAuth } from "@/features/auth/AuthProvider";
import type { InstagramAnalyticsSummary } from "@/features/analytics/types";
import { apiRequest } from "@/services/api";

type AnalyticsPeriod = InstagramAnalyticsSummary["period"];

const periodLabels: Record<AnalyticsPeriod, string> = {
  today: "Hoje",
  yesterday: "Ontem",
  "7d": "Últimos 7 dias",
  "30d": "Últimos 30 dias",
  all: "Todo o período",
};

function formatCount(value: number | null | undefined): string {
  return value == null ? "—" : new Intl.NumberFormat("pt-BR").format(value);
}

function formatDay(day: string): string {
  return new Date(`${day}T00:00:00Z`).toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    timeZone: "UTC",
  });
}

export function DashboardPage() {
  const { user } = useAuth();
  const reduceMotion = useReducedMotion();
  const [period, setPeriod] = useState<AnalyticsPeriod>("7d");
  const summary = useQuery({
    queryKey: ["analytics", "summary", period],
    queryFn: () =>
      apiRequest<InstagramAnalyticsSummary>(
        `/api/analytics/summary?period=${period}`,
      ),
    retry: false,
  });

  const metrics = summary.data;
  const cards = [
    {
      title: "Contas ativas",
      value: formatCount(metrics?.active_accounts),
      detail: "Contas profissionais com autorização válida",
      icon: UsersRound,
      color: "text-[#8295ff]",
    },
    {
      title: "Seguidores",
      value: formatCount(metrics?.followers_count),
      detail: "Soma informada pela Meta na última conexão",
      icon: UsersRound,
      color: "text-[#aab7ff]",
    },
    {
      title: "Posts nos perfis",
      value: formatCount(metrics?.media_count),
      detail: "Publicações existentes nas contas conectadas",
      icon: Eye,
      color: "text-[#71c8e8]",
    },
    {
      title: "Publicados pelo FlashPost",
      value: formatCount(metrics?.published_posts),
      detail: `Publicações concluídas · ${periodLabels[period].toLowerCase()}`,
      icon: CircleCheck,
      color: "text-[#76c8a0]",
    },
    {
      title: "Na fila",
      value: formatCount(metrics?.queued_posts),
      detail: "Publicações aguardando processamento",
      icon: Clock3,
      color: "text-[#f2d48a]",
    },
    {
      title: "Falhas",
      value: formatCount(metrics?.failed_posts),
      detail: "Publicações que precisam de atenção",
      icon: AlertTriangle,
      color: "text-[#f1a3ad]",
    },
  ];

  return (
    <div className="dashboard-ambient mx-auto w-full max-w-[1440px] space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-[#7186ff]">
            Workspace
          </p>
          <h2 className="mt-2 text-2xl font-semibold tracking-[-0.045em] text-[#f5f7fb] sm:text-3xl">
            Visão geral
          </h2>
          <p className="mt-2 text-sm text-[#94a3b8]">
            Acompanhe as contas e as publicações do FlashPost.
          </p>
        </div>
        <label className="flex items-center gap-3 rounded-lg border border-[#27334a] bg-[#0d1015] px-3 py-2 text-xs text-[#94a3b8]">
          Período
          <select
            aria-label="Período do dashboard"
            className="bg-transparent text-sm text-[#f5f7fb] outline-none"
            value={period}
            onChange={(event) => setPeriod(event.target.value as AnalyticsPeriod)}
          >
            {(Object.entries(periodLabels) as [AnalyticsPeriod, string][]).map(
              ([value, label]) => (
                <option className="bg-[#0d1015]" key={value} value={value}>
                  {label}
                </option>
              ),
            )}
          </select>
        </label>
      </header>

      {summary.error && (
        <ErrorState message="Não foi possível carregar as métricas deste workspace." />
      )}
      {summary.isLoading && <LoadingState label="Carregando métricas" />}

      <section aria-label="Métricas do workspace" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {cards.map(({ title, value, detail, icon: Icon, color }) => (
          <article className="dashboard-card min-w-0 rounded-xl p-4 transition-all" key={title}>
            <div className="flex items-center gap-2 text-xs text-[#94a3b8]">
              <Icon className={color} size={16} />
              {title}
            </div>
            <p className="mt-3 truncate text-2xl font-semibold tracking-[-0.035em] text-[#f5f7fb]">
              {value}
            </p>
            <p className="mt-1 text-xs text-[#64748b]">{detail}</p>
          </article>
        ))}
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(280px,0.8fr)]">
        <article className="dashboard-card min-w-0 rounded-xl p-4 sm:p-5">
          <div className="mb-4 flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs font-medium uppercase tracking-[0.13em] text-[#7186ff]">
                Publicações
              </p>
              <h3 className="mt-1 text-sm font-medium text-[#e6eaf2]">
                Atividade · {periodLabels[period]}
              </h3>
            </div>
            <div className="rounded-lg border border-[#27334a] bg-[#090b0f]/70 px-3 py-2">
              <p className="text-[10px] uppercase tracking-[0.12em] text-[#64748b]">
                Total vendido no período
              </p>
              <p className="mt-1 text-lg font-semibold text-[#f2d48a]">R$ —</p>
              <p className="text-[10px] text-[#64748b]">Integração financeira não configurada</p>
            </div>
          </div>
          <div className="h-[280px] w-full">
            <ResponsiveContainer height="100%" width="100%">
              <AreaChart
                data={metrics?.daily_publications ?? []}
                margin={{ top: 8, right: 8, left: -16, bottom: 0 }}
              >
                <defs>
                  <linearGradient id="publishedFill" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%" stopColor="#536dfe" stopOpacity={0.38} />
                    <stop offset="95%" stopColor="#536dfe" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#202838" strokeDasharray="3 3" vertical={false} />
                <XAxis
                  axisLine={false}
                  dataKey="day"
                  tick={{ fill: "#64748b", fontSize: 11 }}
                  tickLine={false}
                  tickFormatter={formatDay}
                />
                <YAxis
                  allowDecimals={false}
                  axisLine={false}
                  tick={{ fill: "#64748b", fontSize: 11 }}
                  tickLine={false}
                />
                <Tooltip
                  contentStyle={{
                    background: "#10141b",
                    border: "1px solid #27334a",
                    borderRadius: 10,
                    color: "#f5f7fb",
                  }}
                  labelFormatter={(day) => `Dia ${formatDay(String(day))}`}
                />
                <Area
                  animationDuration={reduceMotion ? 0 : 450}
                  dataKey="published_posts"
                  fill="url(#publishedFill)"
                  name="Publicações"
                  stroke="#6684ff"
                  strokeWidth={2.5}
                  type="monotone"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          {!metrics?.daily_publications.length && !summary.isLoading && (
            <p className="text-center text-xs text-[#64748b]">
              Ainda não há publicações do FlashPost no período selecionado.
            </p>
          )}
        </article>

        <section className="space-y-3">
          <div className="flex items-center gap-2">
            <Activity className="text-[#7186ff]" size={17} />
            <h3 className="text-sm font-medium text-[#e6eaf2]">Conversões e resultados</h3>
          </div>
          <article className="dashboard-card rounded-xl p-4">
            <div className="flex items-center gap-2 text-xs text-[#94a3b8]">
              <Wallet className="text-[#f2d48a]" size={16} />
              Vendas e conversões
            </div>
            <p className="mt-3 text-xl font-semibold text-[#f2d48a]">Dados indisponíveis</p>
            <p className="mt-1 text-xs leading-5 text-[#64748b]">
              Vendas, Pix, leads e taxas de conversão ainda não são recebidos por uma integração
              neste projeto.
            </p>
          </article>
          <article className="dashboard-card rounded-xl p-4">
            <div className="flex items-center gap-2 text-xs text-[#94a3b8]">
              <Eye className="text-[#71c8e8]" size={16} />
              Alcance e interações
            </div>
            <p className="mt-3 text-xl font-semibold text-[#c7cfdd]">Integração necessária</p>
            <p className="mt-1 text-xs leading-5 text-[#64748b]">
              Impressões, alcance, curtidas e comentários dependem dos Insights da Meta.
            </p>
          </article>
          <p className="px-1 text-xs leading-5 text-[#64748b]">
            Seguidores e posts são os dados recebidos da Meta na última autorização. Contas
            conectadas antes desses campos precisam ser reconectadas para atualizar os snapshots.
            {user?.nickname ? ` Workspace de ${user.nickname}.` : ""}
          </p>
        </section>
      </section>
    </div>
  );
}
