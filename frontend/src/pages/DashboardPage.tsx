import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useReducedMotion } from "framer-motion";
import {
  Activity,
  AlertTriangle,
  CircleCheck,
  Clock3,
  Eye,
  UsersRound,
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
import {
  InstagramAccountSelector,
  type InstagramAccountOption,
} from "@/components/InstagramAccountSelector";
import { useAuth } from "@/features/auth/AuthProvider";
import type { InstagramAnalyticsSummary } from "@/features/analytics/types";
import { apiRequest } from "@/services/api";

type InstagramAccount = InstagramAccountOption & {
  status: "connected" | "disconnected";
  token_expires_at: string;
};

type InstagramAccountsResponse = {
  accounts: InstagramAccount[];
};

function isActive(account: InstagramAccount): boolean {
  return account.status === "connected" && Date.parse(account.token_expires_at) > Date.now();
}

function countLabel(value: number | null, unavailable: string) {
  return value === null
    ? unavailable
    : new Intl.NumberFormat("pt-BR").format(value);
}

export function DashboardPage() {
  const { user } = useAuth();
  const reduceMotion = useReducedMotion();
  const initializedSelection = useRef(false);
  const [selectedAccountIds, setSelectedAccountIds] = useState<string[]>([]);
  const accounts = useQuery({
    queryKey: ["instagram", "accounts"],
    queryFn: () => apiRequest<InstagramAccountsResponse>("/api/instagram/accounts"),
    refetchInterval: 60_000,
    retry: false,
  });
  const activeAccounts = useMemo(
    () => (accounts.data?.accounts ?? []).filter(isActive),
    [accounts.data?.accounts],
  );

  useEffect(() => {
    if (!accounts.data) return;
    if (!initializedSelection.current) {
      initializedSelection.current = true;
      setSelectedAccountIds(activeAccounts.map(({ id }) => id));
      return;
    }
    const activeIds = new Set(activeAccounts.map(({ id }) => id));
    setSelectedAccountIds((current) => {
      const updated = current.filter((id) => activeIds.has(id));
      return updated.length === current.length ? current : updated;
    });
  }, [accounts.data, activeAccounts]);

  const stableSelectedIds = useMemo(
    () => [...selectedAccountIds].sort(),
    [selectedAccountIds],
  );
  const summary = useQuery({
    queryKey: ["analytics", "summary", stableSelectedIds],
    queryFn: () => {
      const query = new URLSearchParams();
      stableSelectedIds.forEach((id) => query.append("account_ids", id));
      return apiRequest<InstagramAnalyticsSummary>(
        `/api/analytics/summary?${query.toString()}`,
      );
    },
    enabled: initializedSelection.current && stableSelectedIds.length > 0,
    retry: false,
  });

  if (accounts.isLoading) return <LoadingState label="Carregando contas do workspace" />;
  if (accounts.error || !accounts.data) {
    return <ErrorState message="Não foi possível carregar as contas deste workspace." />;
  }

  const metrics = summary.data;
  const cards = [
    {
      title: "Contas ativas",
      value: metrics?.active_accounts ?? "—",
      detail: "Contas selecionadas com token válido",
      icon: UsersRound,
      color: "text-[#8295ff]",
    },
    {
      title: "Seguidores",
      value: countLabel(metrics?.followers_count ?? null, "Dados pendentes"),
      detail: "Soma dos perfis selecionados",
      icon: UsersRound,
      color: "text-[#aab7ff]",
    },
    {
      title: "Posts nos perfis",
      value: countLabel(metrics?.media_count ?? null, "Dados pendentes"),
      detail: "Total informado pela Meta na conexão",
      icon: Eye,
      color: "text-[#71c8e8]",
    },
    {
      title: "Publicados pelo FlashPost",
      value: metrics?.published_posts ?? "—",
      detail: "Publicações concluídas",
      icon: CircleCheck,
      color: "text-[#76c8a0]",
    },
    {
      title: "Na fila",
      value: metrics?.queued_posts ?? "—",
      detail: "Aguardando publicação",
      icon: Clock3,
      color: "text-[#f2d48a]",
    },
    {
      title: "Falhas",
      value: metrics?.failed_posts ?? "—",
      detail: "Publicações que precisam de atenção",
      icon: AlertTriangle,
      color: "text-[#f1a3ad]",
    },
  ];

  return (
    <div className="dashboard-ambient mx-auto w-full max-w-[1440px] space-y-6">
      <section className="grid gap-5 xl:grid-cols-[minmax(230px,0.72fr)_minmax(0,2fr)]">
        <InstagramAccountSelector
          accounts={activeAccounts}
          selectedAccountIds={selectedAccountIds}
          onSelectionChange={setSelectedAccountIds}
          label="Contas para consolidar"
        />
        <div className="space-y-5">
          <section>
            <div className="mb-3 flex items-center gap-2">
              <Activity className="text-[#7186ff]" size={17} />
              <h2 className="text-sm font-medium text-[#e6eaf2]">
                Desempenho consolidado
              </h2>
            </div>
            {summary.error && (
              <ErrorState message="Não foi possível carregar as métricas das contas selecionadas." />
            )}
            {summary.isLoading && <LoadingState label="Carregando métricas" />}
            <div className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-3">
              {cards.map(({ title, value, detail, icon: Icon, color }) => (
                <article
                  className="min-w-0 rounded-xl border border-[#202838] bg-[#0d1015] p-4"
                  key={title}
                >
                  <div className="flex items-center gap-2 text-xs text-[#94a3b8]">
                    <Icon className={color} size={15} />
                    {title}
                  </div>
                  <p className="mt-3 truncate text-2xl font-semibold tracking-[-0.035em] text-[#f5f7fb]">
                    {selectedAccountIds.length ? value : "—"}
                  </p>
                  <p className="mt-1 text-xs text-[#64748b]">{detail}</p>
                </article>
              ))}
            </div>
          </section>
          <section className="rounded-xl border border-[#202838] bg-[#0d1015] p-4 sm:p-5">
            <div className="mb-4">
              <p className="text-xs font-medium uppercase tracking-[0.13em] text-[#7186ff]">
                Publicações
              </p>
              <h2 className="mt-1 text-sm font-medium text-[#e6eaf2]">
                Atividade nos últimos 7 dias
              </h2>
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
                    tickFormatter={(day: string) =>
                      new Date(`${day}T00:00:00Z`).toLocaleDateString("pt-BR", {
                        day: "2-digit",
                        month: "2-digit",
                        timeZone: "UTC",
                      })
                    }
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
                    labelFormatter={(day) => `Dia ${day}`}
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
            {!selectedAccountIds.length && (
              <p className="text-center text-xs text-[#64748b]">
                Selecione uma ou mais contas para ver os dados consolidados.
              </p>
            )}
            {selectedAccountIds.length > 0 && !metrics?.daily_publications.length && (
              <p className="text-center text-xs text-[#64748b]">
                Ainda não há publicações do FlashPost no período selecionado.
              </p>
            )}
          </section>
        </div>
      </section>
      <p className="text-xs leading-5 text-[#64748b]">
        Seguidores e quantidade de posts são os dados recebidos da Meta na última autorização da
        conta; contas conectadas antes da inclusão desses dados precisam ser reconectadas uma vez.
        Impressões, alcance e interações dependem da integração de Insights da Meta.
        {user?.full_name ? ` Dados do workspace de ${user.full_name}.` : ""}
      </p>
    </div>
  );
}
