import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, BarChart3, CircleCheck, Clock3, Eye, UsersRound } from "lucide-react";
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
import { InstagramAvatar } from "@/components/InstagramAvatar";
import {
  InstagramAccountSelector,
  type InstagramAccountOption,
} from "@/components/InstagramAccountSelector";
import type { InstagramAnalyticsSummary } from "@/features/analytics/types";
import { apiRequest } from "@/services/api";

type Account = InstagramAccountOption & {
  status: "connected" | "disconnected";
  token_expires_at: string;
};

function formatCount(value: number | null | undefined): string {
  return value === null || value === undefined
    ? "Não disponível"
    : new Intl.NumberFormat("pt-BR").format(value);
}

export function AnalyticsPage() {
  const [selectedAccountIds, setSelectedAccountIds] = useState<string[]>([]);
  const accounts = useQuery({
    queryKey: ["instagram", "accounts"],
    queryFn: () => apiRequest<{ accounts: Account[] }>("/api/instagram/accounts"),
    refetchInterval: 60_000,
    retry: false,
  });
  const activeAccounts = useMemo(
    () =>
      (accounts.data?.accounts ?? []).filter(
        (account) =>
          account.status === "connected" && Date.parse(account.token_expires_at) > Date.now(),
      ),
    [accounts.data?.accounts],
  );
  const selectedAccountId = selectedAccountIds[0];

  useEffect(() => {
    if (selectedAccountId && activeAccounts.some(({ id }) => id === selectedAccountId)) return;
    const nextId = activeAccounts[0]?.id;
    if (nextId !== selectedAccountId) setSelectedAccountIds(nextId ? [nextId] : []);
  }, [activeAccounts, selectedAccountId]);
  const summary = useQuery({
    queryKey: ["analytics", "account", selectedAccountId],
    queryFn: () => {
      const query = new URLSearchParams();
      query.append("account_ids", selectedAccountId);
      return apiRequest<InstagramAnalyticsSummary>(
        `/api/analytics/summary?${query.toString()}`,
      );
    },
    enabled: Boolean(selectedAccountId),
    retry: false,
  });
  const accountMetrics = summary.data?.accounts[0];
  const metrics = [
    {
      title: "Seguidores",
      value: formatCount(accountMetrics?.follower_count),
      helper: "Informado pela Meta na última autorização",
      icon: UsersRound,
    },
    {
      title: "Posts no perfil",
      value: formatCount(accountMetrics?.media_count),
      helper: "Total informado pela Meta na última autorização",
      icon: BarChart3,
    },
    {
      title: "Publicados pelo FlashPost",
      value: formatCount(accountMetrics?.published_posts),
      helper: "Publicações concluídas pela ferramenta",
      icon: CircleCheck,
    },
    {
      title: "Na fila",
      value: formatCount(accountMetrics?.queued_posts),
      helper: "Aguardando envio ou processamento",
      icon: Clock3,
    },
    {
      title: "Falhas",
      value: formatCount(accountMetrics?.failed_posts),
      helper: "Publicações que precisam de atenção",
      icon: AlertTriangle,
    },
    {
      title: "Impressões",
      value: "Não disponível",
      helper: "Requer leitura dos Insights da Meta",
      icon: Eye,
    },
    {
      title: "Visualizações",
      value: "Não disponível",
      helper: "Requer leitura dos Insights da Meta",
      icon: Eye,
    },
    {
      title: "Curtidas",
      value: "Não disponível",
      helper: "Requer leitura dos Insights da Meta",
      icon: BarChart3,
    },
    {
      title: "Comentários",
      value: "Não disponível",
      helper: "Requer leitura dos Insights da Meta",
      icon: BarChart3,
    },
    {
      title: "Compartilhamentos",
      value: "Não disponível",
      helper: "Requer leitura dos Insights de cada publicação",
      icon: BarChart3,
    },
  ];

  if (accounts.isLoading) return <LoadingState label="Carregando contas para Analytics" />;
  if (accounts.error || !accounts.data) {
    return <ErrorState message="Não foi possível carregar as contas deste workspace." />;
  }

  return (
    <div className="mx-auto max-w-[1440px] space-y-6">
      <header>
        <p className="text-xs font-medium uppercase tracking-[0.16em] text-[#7186ff]">Métricas</p>
        <h2 className="mt-2 text-2xl font-semibold tracking-[-0.045em] text-[#f5f7fb] sm:text-3xl">
          Analytics por conta
        </h2>
        <p className="mt-2 text-sm leading-6 text-[#94a3b8]">
          Selecione uma conta para consultar seus dados sem misturá-los com os das outras.
        </p>
      </header>
      <div className="grid gap-5 lg:grid-cols-[260px_minmax(0,1fr)]">
        <InstagramAccountSelector
          accounts={activeAccounts}
          selectedAccountIds={selectedAccountIds}
          onSelectionChange={setSelectedAccountIds}
          selectionMode="single"
          label="Conta Instagram"
        />
        <div className="min-w-0 space-y-5">
          {!activeAccounts.length ? (
            <section className="rounded-xl border border-dashed border-[#27334a] p-8 text-center text-sm text-[#94a3b8]">
              Conecte uma conta ativa no Hub de Contas para consultar o Analytics.
            </section>
          ) : (
            <>
              <div className="flex items-center gap-3">
                <InstagramAvatar
                  className="size-10 rounded-full object-cover"
                  src={accountMetrics?.profile_picture_url ?? null}
                  username={
                    accountMetrics?.username ??
                    activeAccounts.find(({ id }) => id === selectedAccountId)?.username ??
                    "Instagram"
                  }
                />
                <div>
                  <p className="text-xs uppercase tracking-[0.13em] text-[#7186ff]">Conta atual</p>
                  <h3 className="font-medium text-[#f5f7fb]">
                    @{accountMetrics?.username ?? activeAccounts.find(({ id }) => id === selectedAccountId)?.username}
                  </h3>
                </div>
              </div>
              {summary.error && (
                <ErrorState message="Não foi possível carregar as métricas desta conta." />
              )}
              {summary.isLoading && <LoadingState label="Carregando dados da conta" />}
              <div className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-4">
                {metrics.map(({ title, value, helper, icon: Icon }) => (
                  <article
                    className="rounded-xl border border-[#202838] bg-[#0d1015] p-4"
                    key={title}
                  >
                    <div className="flex items-center gap-2 text-xs text-[#94a3b8]">
                      <Icon className="text-[#8295ff]" size={15} />
                      {title}
                    </div>
                    <p className="mt-3 text-xl font-semibold text-[#f5f7fb]">{value}</p>
                    <p className="mt-1 text-xs leading-5 text-[#64748b]">{helper}</p>
                  </article>
                ))}
              </div>
              <section className="rounded-xl border border-[#202838] bg-[#0d1015] p-4 sm:p-5">
                <h3 className="text-sm font-medium text-[#e6eaf2]">
                  Publicações dos últimos 7 dias
                </h3>
                <div className="mt-4 h-[260px]">
                  <ResponsiveContainer height="100%" width="100%">
                    <AreaChart data={summary.data?.daily_publications ?? []}>
                      <defs>
                        <linearGradient id="accountPublishedFill" x1="0" x2="0" y1="0" y2="1">
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
                      />
                      <Area
                        dataKey="published_posts"
                        fill="url(#accountPublishedFill)"
                        name="Publicações"
                        stroke="#6684ff"
                        strokeWidth={2.5}
                        type="monotone"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </section>
              <p className="rounded-lg border border-[#27334a] bg-[#10141b] px-4 py-3 text-xs leading-5 text-[#94a3b8]">
                Impressões, alcance, visualizações e interações não são preenchidos com dados
                estimados: a integração atual não consulta os Insights da Meta. Seguidores e posts
                no perfil são uma fotografia dos valores retornados durante a última autorização da
                conta.
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
