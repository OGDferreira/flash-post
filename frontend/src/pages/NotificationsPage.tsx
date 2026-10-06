import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, RefreshCw } from "lucide-react";

import { ErrorState, LoadingState } from "@/components/PageState";
import { apiRequest } from "@/services/api";
import type { InstagramAnalyticsSummary } from "@/features/analytics/types";

type AccountList = {
  accounts: {
    id: string;
    username: string;
    status: "connected" | "disconnected" | "error";
    status_reason: string | null;
    error_at: string | null;
    connected_at: string;
    token_expires_at: string;
  }[];
};

type PublicationFailures = {
  failures: {
    id: string;
    account_id: string;
    loop_name: string;
    account_username: string;
    media_filename: string | null;
    updated_at: string;
    attempts: number;
    error: string;
  }[];
};

function dateTime(value: string | null) {
  if (!value) return "Horário indisponível";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Horário indisponível";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "America/Sao_Paulo",
  }).format(date);
}

export function NotificationsPage() {
  const accounts = useQuery({
    queryKey: ["instagram", "accounts"],
    queryFn: () => apiRequest<AccountList>("/api/instagram/accounts"),
    refetchInterval: 60_000,
    retry: false,
  });
  const failures = useQuery({
    queryKey: ["loops", "failures"],
    queryFn: () => apiRequest<PublicationFailures>("/api/loops/failures"),
    refetchInterval: 60_000,
    retry: false,
  });
  const metrics = useQuery({
    queryKey: ["analytics", "summary", "7d", null, null],
    queryFn: () =>
      apiRequest<InstagramAnalyticsSummary>(
        "/api/analytics/summary?period=7d&include_meta_insights=true",
      ),
    refetchInterval: 300_000,
    retry: false,
  });

  const hasLoading = accounts.isLoading || failures.isLoading || metrics.isLoading;
  const insightsIssues =
    metrics.data?.accounts.filter(
      (account) =>
        account.status === "connected" &&
        (account.insights_error || account.profile_metrics_error),
    ) ?? [];
  const activeFailures =
    failures.data?.failures.filter((failure) =>
      accounts.data?.accounts.some(
        (account) =>
          account.id === failure.account_id &&
          account.status === "connected" &&
          Date.parse(failure.updated_at) > Date.parse(account.connected_at),
      ),
    ) ?? [];
  const hasIssues =
    insightsIssues.length > 0 ||
    activeFailures.length > 0 ||
    (metrics.data?.missing_permissions.length ?? 0) > 0 ||
    metrics.data?.insights_unavailable === true ||
    metrics.data?.profile_metrics_unavailable === true;

  return (
    <div className="mx-auto max-w-[1100px] space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-[#8295ff]">
            Sistema e workspace
          </p>
          <h1 className="mt-2 text-2xl font-semibold text-[#f5f7fb] sm:text-3xl">
            Central de notificações
          </h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-[#94a3b8]">
            Alertas de métricas da Meta e de publicações recentes. Contas com erro
            ou desconectadas ficam na aba oculta de erros do Hub de contas.
          </p>
        </div>
        <button
          className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-[#27334a] px-3 text-sm text-[#cbd5e1] hover:bg-[#101923]"
          onClick={() => {
            void accounts.refetch();
            void failures.refetch();
            void metrics.refetch();
          }}
          type="button"
        >
          <RefreshCw size={14} />
          Atualizar
        </button>
      </header>

      <aside className="rounded-lg border border-[#27334a] bg-[#0d1015] p-4 text-xs leading-5 text-[#94a3b8]">
        Os detalhes abaixo vêm dos retornos da Meta, do estado das contas e dos
        erros de publicação guardados pelo FlashPost. O Render não disponibiliza
        os logs brutos ao aplicativo sem uma integração autenticada; para
        consultar logs de deploy e servidor, use a seção Logs do serviço no
        Render.
      </aside>

      {hasLoading && <LoadingState label="Carregando diagnósticos do workspace" />}
      {(accounts.error || failures.error || metrics.error) && (
        <ErrorState message="Uma ou mais fontes de diagnóstico estão indisponíveis. Atualize para tentar novamente." />
      )}

      {!hasLoading && !hasIssues && (
        <section className="dashboard-card flex items-center gap-3 rounded-xl p-5">
          <CheckCircle2 className="text-[#76c8a0]" size={20} />
          <div>
            <h2 className="font-medium text-[#e6eaf2]">Nenhum problema registrado</h2>
            <p className="mt-1 text-xs text-[#94a3b8]">
              Contas, Insights e publicações não reportaram erros recentes.
            </p>
          </div>
        </section>
      )}

      {(metrics.data?.insights_unavailable ||
        metrics.data?.missing_permissions.length ||
        metrics.data?.profile_metrics_unavailable) && (
        <section className="dashboard-card rounded-xl p-5">
          <h2 className="flex items-center gap-2 font-semibold text-[#f2d48a]">
            <AlertTriangle size={16} />
            Métricas da Meta
          </h2>
          {metrics.data.missing_permissions.length > 0 && (
            <p className="mt-3 rounded-lg border border-[#544526] bg-[#211c10] p-3 text-sm text-[#f2d48a]">
              Permissão sinalizada pela Meta:{" "}
              {metrics.data.missing_permissions.join(", ")}. Reconecte a conta
              para conceder a permissão ao token.
            </p>
          )}
          {insightsIssues.length > 0 ? (
            <ul className="mt-3 divide-y divide-[#202838]">
              {insightsIssues.map((account) => (
                <li className="py-3 first:pt-0 last:pb-0" key={account.account_id}>
                  <p className="text-sm font-medium text-[#e6eaf2]">
                    @{account.username}
                  </p>
                  {account.insights_error && (
                    <p className="mt-1 text-xs leading-5 text-[#f1a3ad]">
                      Insights: {account.insights_error}
                    </p>
                  )}
                  {account.profile_metrics_error && (
                    <p className="mt-1 text-xs leading-5 text-[#f2d48a]">
                      Seguidores/posts: {account.profile_metrics_error}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-sm text-[#94a3b8]">
              A Meta não retornou todas as métricas, mas não forneceu detalhes
              por conta nesta consulta. O último snapshot permanece disponível
              quando existe.
            </p>
          )}
        </section>
      )}

      {activeFailures.length > 0 && (
        <section className="dashboard-card rounded-xl p-5">
          <h2 className="flex items-center gap-2 font-semibold text-[#f1a3ad]">
            <AlertTriangle size={16} />
            Publicações com falha ({activeFailures.length})
          </h2>
          <ul className="mt-4 divide-y divide-[#202838]">
            {activeFailures.map((failure) => (
              <li className="py-3 first:pt-0 last:pb-0" key={failure.id}>
                <div className="flex flex-wrap justify-between gap-2">
                  <p className="text-sm font-medium text-[#e6eaf2]">
                    @{failure.account_username} · {failure.loop_name}
                  </p>
                  <p className="text-xs text-[#94a3b8]">
                    {dateTime(failure.updated_at)} · {failure.attempts} tentativas
                  </p>
                </div>
                {failure.media_filename && (
                  <p className="mt-1 text-xs text-[#94a3b8]">
                    Mídia: {failure.media_filename}
                  </p>
                )}
                <p className="mt-1 break-words text-xs leading-5 text-[#f1a3ad]">
                  {failure.error}
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
