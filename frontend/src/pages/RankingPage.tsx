import { useQuery } from "@tanstack/react-query";
import { Medal, UsersRound } from "lucide-react";
import { useState } from "react";

import { ErrorState, LoadingState } from "@/components/PageState";
import { apiRequest } from "@/services/api";

type RankingPeriod = "today" | "yesterday" | "7d" | "30d" | "all";

type RankingResponse = {
  period: string;
  days_in_period: number;
  total_connections: number;
  collaborators: {
    user_id: string;
    full_name: string;
    nickname: string;
    connections: number;
    average_daily_connections: number;
    position: number;
  }[];
};

const periods: { value: RankingPeriod; label: string }[] = [
  { value: "today", label: "Hoje" },
  { value: "yesterday", label: "Ontem" },
  { value: "7d", label: "7 dias" },
  { value: "30d", label: "30 dias" },
  { value: "all", label: "Todo o período" },
];

function count(value: number) {
  return new Intl.NumberFormat("pt-BR").format(value);
}

function average(value: number) {
  return new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

export function RankingPage() {
  const [period, setPeriod] = useState<RankingPeriod>("30d");
  const ranking = useQuery({
    queryKey: ["collaborators", "ranking", period],
    queryFn: () =>
      apiRequest<RankingResponse>(
        `/api/collaborators/ranking?period=${period}`,
      ),
    retry: false,
  });

  return (
    <div className="mx-auto max-w-[1320px] space-y-6">
      <header>
        <p className="text-xs font-medium uppercase tracking-[0.16em] text-[#8295ff]">
          Equipe
        </p>
        <h1 className="mt-2 text-2xl font-semibold text-[#f5f7fb] sm:text-3xl">
          Ranking de conexões
        </h1>
        <p className="mt-2 text-sm text-[#94a3b8]">
          Compare as contas conectadas pelo chefe e pelos colaboradores.
        </p>
      </header>

      <nav
        aria-label="Período do ranking"
        className="flex flex-wrap gap-2 rounded-xl border border-[#202838] bg-[#0d1015] p-2"
      >
        {periods.map((option) => (
          <button
            aria-pressed={period === option.value}
            className={`min-h-9 rounded-lg px-3 text-xs font-medium transition ${
              period === option.value
                ? "bg-[#536dfe] text-white"
                : "text-[#94a3b8] hover:bg-[#171e31] hover:text-white"
            }`}
            key={option.value}
            onClick={() => setPeriod(option.value)}
            type="button"
          >
            {option.label}
          </button>
        ))}
      </nav>

      {ranking.isLoading ? (
        <LoadingState label="Carregando ranking da equipe" />
      ) : ranking.error || !ranking.data ? (
        <ErrorState message="Não foi possível carregar as conexões da equipe." />
      ) : (
        <>
          <section className="grid gap-3 sm:grid-cols-2">
            <article className="dashboard-card rounded-xl p-5">
              <div className="flex items-center gap-2 text-xs text-[#94a3b8]">
                <UsersRound className="text-[#8295ff]" size={16} />
                Contas conectadas no período
              </div>
              <p className="mt-2 text-3xl font-semibold text-[#f5f7fb]">
                {count(ranking.data.total_connections)}
              </p>
            </article>
            <article className="dashboard-card rounded-xl p-5">
              <div className="flex items-center gap-2 text-xs text-[#94a3b8]">
                <Medal className="text-[#f2d48a]" size={16} />
                Dias considerados na média
              </div>
              <p className="mt-2 text-3xl font-semibold text-[#f5f7fb]">
                {count(ranking.data.days_in_period)}
              </p>
            </article>
          </section>

          <section className="dashboard-card overflow-hidden rounded-xl">
            <div className="border-b border-[#202838] px-5 py-4">
              <h2 className="font-semibold text-[#f5f7fb]">
                Produção por integrante
              </h2>
              <p className="mt-1 text-xs text-[#94a3b8]">
                Média diária = contas conectadas ÷ dias do período selecionado.
              </p>
            </div>
            {ranking.data.collaborators.length ? (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[560px] text-left text-sm">
                  <thead className="bg-[#0d1015] text-xs text-[#94a3b8]">
                    <tr>
                      <th className="px-5 py-3 font-medium">Posição</th>
                      <th className="px-5 py-3 font-medium">Integrante</th>
                      <th className="px-5 py-3 text-right font-medium">
                        Contas conectadas
                      </th>
                      <th className="px-5 py-3 text-right font-medium">
                        Média por dia
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {ranking.data.collaborators.map((member) => (
                      <tr
                        className="border-t border-[#202838] text-[#e6eaf2]"
                        key={member.user_id}
                      >
                        <td className="px-5 py-3 font-semibold text-[#f2d48a]">
                          #{member.position}
                        </td>
                        <td className="px-5 py-3">
                          <span className="font-medium">{member.full_name}</span>
                          <span className="ml-2 text-xs text-[#718096]">
                            @{member.nickname}
                          </span>
                        </td>
                        <td className="px-5 py-3 text-right font-semibold">
                          {count(member.connections)}
                        </td>
                        <td className="px-5 py-3 text-right text-[#aab7ff]">
                          {average(member.average_daily_connections)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="p-5 text-sm text-[#94a3b8]">
                Não há integrantes ativos neste workspace.
              </p>
            )}
          </section>
        </>
      )}
    </div>
  );
}
