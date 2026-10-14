import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Download, RefreshCw, RotateCcw } from "lucide-react";

import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { apiRequest } from "@/services/api";

type DiagnosticsEvent = {
  id: string;
  source: "browser" | "client_api" | "server";
  level: "error" | "warning";
  message: string;
  stack: string | null;
  path: string;
  category: string | null;
  meta_code: number | null;
  account_id: string | null;
  loop_id: string | null;
  created_at: string;
};

type DiagnosticsResponse = { events: DiagnosticsEvent[] };
type EventFilter = "all" | DiagnosticsEvent["source"];

const categoryLabels: Record<string, string> = {
  token: "Token / conta",
  rate_limit: "Limite da Meta",
  storage: "Storage",
  network: "Rede",
  video_format: "Formato do vídeo",
  meta_api: "API da Meta",
  unknown: "Desconhecido",
};

const periodOptions = [
  ["", "Todo o período"],
  ["1", "Últimas 24 horas"],
  ["7", "Últimos 7 dias"],
] as const;

const sourceLabels: Record<DiagnosticsEvent["source"], string> = {
  browser: "Navegador / F12",
  client_api: "Resposta da API",
  server: "Servidor",
};

function formatDate(value: string): string {
  return new Date(value).toLocaleString("pt-BR", {
    dateStyle: "short",
    timeStyle: "medium",
    timeZone: "America/Sao_Paulo",
  });
}

export function ErrorLogsPage() {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<EventFilter>("all");
  const [category, setCategory] = useState("");
  const [search, setSearch] = useState("");
  const [period, setPeriod] = useState("");
  const [retryMessage, setRetryMessage] = useState<string | null>(null);
  const params = new URLSearchParams({ limit: "300" });
  if (filter !== "all") params.set("source", filter);
  if (category) params.set("category", category);
  if (search.trim()) params.set("q", search.trim());
  if (period) {
    params.set("since", new Date(Date.now() - Number(period) * 86_400_000).toISOString());
  }
  const events = useQuery({
    queryKey: ["diagnostics", "events", params.toString()],
    queryFn: () => apiRequest<DiagnosticsResponse>(`/api/diagnostics/events?${params}`),
    retry: false,
    refetchInterval: 30_000,
  });
  const retryFailures = useMutation({
    mutationFn: () =>
      apiRequest<{ requeued: number }>("/api/loops/failures/retry", {
        method: "POST",
        body: {},
      }),
    onSuccess: (data) => {
      setRetryMessage(`${data.requeued} publicações de hoje voltaram para a fila.`);
      void queryClient.invalidateQueries({ queryKey: ["loops"] });
    },
    onError: () => setRetryMessage("Não foi possível reenviar as falhas."),
  });
  const visibleEvents = events.data?.events ?? [];

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-[#7186ff]">
            Diagnóstico
          </p>
          <h2 className="mt-2 text-2xl font-semibold tracking-[-0.045em] text-[#f5f7fb]">
            Log de erros
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-[#94a3b8]">
            Erros JavaScript e do console do navegador, respostas 5xx da API e erros
            inesperados registrados pelo servidor deste workspace.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-[#536dfe] px-3 py-2 text-sm text-white hover:bg-[#171d35] disabled:opacity-60"
            disabled={retryFailures.isPending}
            onClick={() => retryFailures.mutate()}
            type="button"
          >
            <RotateCcw size={15} />
            Reenviar falhas de hoje
          </button>
          <a
            className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-line px-3 py-2 text-sm text-[#dbe4f3] hover:bg-[#101923]"
            href={`/api/diagnostics/events.csv?${params}`}
          >
            <Download size={15} />
            Exportar CSV
          </a>
          <button
            className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-line px-3 py-2 text-sm text-[#dbe4f3] hover:bg-[#101923] disabled:opacity-60"
            disabled={events.isFetching}
            onClick={() => void events.refetch()}
            type="button"
          >
            <RefreshCw size={15} />
            Atualizar
          </button>
        </div>
      </header>

      {retryMessage && (
        <p className="rounded-lg border border-line bg-[#101923] px-3 py-2 text-sm text-[#dbe4f3]" role="status">
          {retryMessage}
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        <input
          aria-label="Buscar no log"
          className="min-h-10 rounded-lg border border-line bg-surface-inset px-3 text-sm text-white placeholder:text-[#64748b]"
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Buscar conta, vídeo ou texto"
          value={search}
        />
        <select
          aria-label="Categoria"
          className="min-h-10 rounded-lg border border-line bg-surface-inset px-3 text-sm text-white"
          onChange={(event) => setCategory(event.target.value)}
          value={category}
        >
          <option value="">Todas as categorias</option>
          {Object.entries(categoryLabels).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <select
          aria-label="Período"
          className="min-h-10 rounded-lg border border-line bg-surface-inset px-3 text-sm text-white"
          onChange={(event) => setPeriod(event.target.value)}
          value={period}
        >
          {periodOptions.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-wrap gap-2" role="group" aria-label="Filtrar origem dos erros">
        {(
          [
            ["all", "Todos"],
            ["browser", "Navegador / F12"],
            ["client_api", "API"],
            ["server", "Servidor"],
          ] as const
        ).map(([value, label]) => (
          <button
            aria-pressed={filter === value}
            className={`rounded-lg border px-3 py-2 text-xs ${
              filter === value
                ? "border-[#536dfe] bg-[#171d35] text-white"
                : "border-line text-[#94a3b8] hover:text-white"
            }`}
            key={value}
            onClick={() => setFilter(value)}
            type="button"
          >
            {label}
          </button>
        ))}
      </div>

      {events.isLoading ? (
        <LoadingState label="Carregando log de erros" />
      ) : events.error || !events.data ? (
        <ErrorState message="Não foi possível carregar os erros registrados." />
      ) : visibleEvents.length === 0 ? (
        <EmptyState message="Nenhum erro registrado para este filtro." />
      ) : (
        <section aria-label="Erros registrados" className="space-y-3">
          {visibleEvents.map((event) => (
            <article
              className="rounded-xl border border-[#47252d] bg-[#130e11] p-4"
              key={event.id}
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="inline-flex items-center gap-2 text-sm font-medium text-[#f1a3ad]">
                  <AlertTriangle size={15} />
                  {sourceLabels[event.source]}
                  {event.category && (
                    <span className="rounded bg-[#2a1a20] px-2 py-0.5 text-xs text-[#f5c0c8]">
                      {categoryLabels[event.category] ?? event.category}
                      {event.meta_code ? ` · código ${event.meta_code}` : ""}
                    </span>
                  )}
                </span>
                <time className="text-xs text-[#94a3b8]">{formatDate(event.created_at)}</time>
              </div>
              <p className="mt-2 break-words text-sm leading-6 text-[#f5f7fb]">
                {event.message}
              </p>
              <p className="mt-1 break-all text-xs text-[#94a3b8]">{event.path}</p>
              {event.stack && (
                <details className="mt-3">
                  <summary className="cursor-pointer text-xs text-[#aab7ff]">
                    Detalhes técnicos
                  </summary>
                  <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-surface-inset p-3 text-xs leading-5 text-[#cbd5e1]">
                    {event.stack}
                  </pre>
                </details>
              )}
            </article>
          ))}
        </section>
      )}
    </div>
  );
}
