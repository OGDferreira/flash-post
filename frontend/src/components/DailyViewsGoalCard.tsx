import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, BellOff, RefreshCw, Send, Target } from "lucide-react";

import {
  currentSubscription,
  disablePush,
  enablePush,
  pushAvailability,
  type PushConfig,
} from "@/lib/push";
import { ApiError, apiRequest } from "@/services/api";

export type DailyViewsGoal = {
  user_id: string;
  full_name: string | null;
  role: string | null;
  configured: boolean;
  target_views: number | null;
  enabled: boolean;
  timezone: string;
  progress_date: string | null;
  progress_views: number | null;
  progress_accounts: number | null;
  progress_checked_at: string | null;
  progress_error: string | null;
  notified_today: boolean;
};

const BRAZIL_TIME_ZONES: [string, string][] = [
  ["America/Sao_Paulo", "Brasília (SP, RJ, MG, Sul, GO, DF)"],
  ["America/Bahia", "Bahia"],
  ["America/Fortaleza", "Fortaleza (CE, RN, PB, PI, MA)"],
  ["America/Recife", "Recife (PE)"],
  ["America/Belem", "Belém (PA, AP)"],
  ["America/Manaus", "Manaus (AM)"],
  ["America/Cuiaba", "Cuiabá (MT)"],
  ["America/Campo_Grande", "Campo Grande (MS)"],
  ["America/Porto_Velho", "Porto Velho (RO)"],
  ["America/Boa_Vista", "Boa Vista (RR)"],
  ["America/Rio_Branco", "Rio Branco (AC)"],
  ["America/Noronha", "Fernando de Noronha"],
];

const numberFormat = new Intl.NumberFormat("pt-BR");

function errorMessage(error: unknown) {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "Não foi possível concluir a ação.";
}

export function DailyViewsGoalCard() {
  const queryClient = useQueryClient();
  const goal = useQuery({
    queryKey: ["notifications", "goal", "me"],
    queryFn: () => apiRequest<DailyViewsGoal>("/api/notifications/goals/me"),
    staleTime: 60_000,
    refetchInterval: 5 * 60_000,
  });
  const pushConfig = useQuery({
    queryKey: ["notifications", "push", "config"],
    queryFn: () => apiRequest<PushConfig>("/api/notifications/push/config"),
    staleTime: 5 * 60_000,
  });
  const availability = useMemo(() => pushAvailability(), []);
  const [subscribedHere, setSubscribedHere] = useState<boolean | null>(null);
  const [target, setTarget] = useState("");
  const [timeZone, setTimeZone] = useState("America/Sao_Paulo");
  const [enabled, setEnabled] = useState(true);
  const [feedback, setFeedback] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  useEffect(() => {
    if (!goal.data) return;
    setTarget(goal.data.target_views ? String(goal.data.target_views) : "");
    setTimeZone(goal.data.timezone);
    setEnabled(goal.data.configured ? goal.data.enabled : true);
  }, [goal.data]);

  useEffect(() => {
    let cancelled = false;
    void currentSubscription()
      .then((subscription) => !cancelled && setSubscribedHere(Boolean(subscription)))
      .catch(() => !cancelled && setSubscribedHere(false));
    return () => {
      cancelled = true;
    };
  }, []);

  const zoneOptions = useMemo(() => {
    const deviceZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    const options = [...BRAZIL_TIME_ZONES];
    for (const zone of [deviceZone, goal.data?.timezone]) {
      if (zone && !options.some(([value]) => value === zone)) options.push([zone, zone]);
    }
    return options;
  }, [goal.data?.timezone]);

  const save = useMutation({
    mutationFn: () =>
      apiRequest<DailyViewsGoal>("/api/notifications/goals/me", {
        method: "PUT",
        body: { target_views: Number(target), enabled, timezone: timeZone },
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(["notifications", "goal", "me"], data);
      setFeedback({ kind: "ok", text: "Meta salva." });
    },
    onError: (error) => setFeedback({ kind: "error", text: errorMessage(error) }),
  });
  const refresh = useMutation({
    mutationFn: () =>
      apiRequest<DailyViewsGoal>("/api/notifications/goals/me/refresh", { method: "POST" }),
    onSuccess: (data) => queryClient.setQueryData(["notifications", "goal", "me"], data),
    onError: (error) => setFeedback({ kind: "error", text: errorMessage(error) }),
  });
  const togglePush = useMutation({
    mutationFn: async () => {
      if (subscribedHere) {
        await disablePush();
        return false;
      }
      const key = pushConfig.data?.public_key;
      if (!key) throw new Error("Notificações push indisponíveis no servidor.");
      await enablePush(key);
      return true;
    },
    onSuccess: (active) => {
      setSubscribedHere(active);
      void queryClient.invalidateQueries({ queryKey: ["notifications", "push", "config"] });
      setFeedback({
        kind: "ok",
        text: active ? "Notificações ativadas neste dispositivo." : "Notificações desativadas neste dispositivo.",
      });
    },
    onError: (error) => setFeedback({ kind: "error", text: errorMessage(error) }),
  });
  const testPush = useMutation({
    mutationFn: () =>
      apiRequest<{ delivered: number; devices: number }>("/api/notifications/push/test", {
        method: "POST",
      }),
    onSuccess: ({ delivered, devices }) =>
      setFeedback(
        delivered
          ? { kind: "ok", text: `Teste enviado para ${delivered} de ${devices} dispositivo(s).` }
          : { kind: "error", text: "Nenhum dispositivo recebeu o teste. Ative as notificações primeiro." },
      ),
    onError: (error) => setFeedback({ kind: "error", text: errorMessage(error) }),
  });

  const data = goal.data;
  const progress =
    data?.target_views && data.progress_views !== null
      ? Math.min(100, Math.round((data.progress_views / data.target_views) * 100))
      : null;
  const targetValid = Number.isInteger(Number(target)) && Number(target) >= 1;

  return (
    <section className="glass-panel p-4 sm:p-5" aria-labelledby="daily-goal-title">
      <header className="flex items-start gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-xl border border-line bg-brand-soft text-accent">
          <Target size={18} />
        </span>
        <div>
          <h2 id="daily-goal-title" className="text-lg font-semibold text-fg">
            Meta diária de visualizações
          </h2>
          <p className="mt-1 text-sm leading-6 text-muted">
            Receba um aviso no celular quando suas contas atingirem a meta do dia, mesmo com o app fechado.
          </p>
        </div>
      </header>

      {goal.isLoading ? (
        <div className="mt-6 space-y-3" aria-busy="true">
          <div className="skeleton h-16" />
          <div className="skeleton h-11" />
        </div>
      ) : goal.error ? (
        <p className="mt-6 text-sm text-danger">Não foi possível carregar sua meta.</p>
      ) : (
        <>
          {data?.configured && (
            <div className="mt-6 rounded-2xl border border-line bg-surface-inset p-4">
              <div className="flex items-baseline justify-between gap-3">
                <p className="text-xs uppercase tracking-[0.12em] text-muted">Hoje</p>
                <button
                  className="btn-ghost min-h-9 !px-2 text-xs"
                  disabled={refresh.isPending}
                  onClick={() => refresh.mutate()}
                  type="button"
                >
                  <RefreshCw className={refresh.isPending ? "animate-spin" : ""} size={14} />
                  Atualizar
                </button>
              </div>
              <p className="mt-1 text-2xl font-semibold tracking-[-0.03em] text-fg">
                {data.progress_views === null ? "—" : numberFormat.format(data.progress_views)}
                <span className="text-sm font-normal text-muted">
                  {" "}
                  / {numberFormat.format(data.target_views ?? 0)}
                </span>
              </p>
              <div
                aria-label="Progresso da meta"
                aria-valuemax={100}
                aria-valuemin={0}
                aria-valuenow={progress ?? undefined}
                className="mt-3 h-2 overflow-hidden rounded-full bg-white/5"
                role="progressbar"
              >
                <div
                  className="h-full rounded-full bg-gradient-to-r from-[#536dfe] to-[#00c9d8] transition-[width] duration-500"
                  style={{ width: `${progress ?? 0}%` }}
                />
              </div>
              <p className="mt-2 text-xs leading-5 text-muted">
                {data.notified_today
                  ? "Meta atingida hoje — notificação enviada."
                  : data.progress_error
                    ? data.progress_error
                    : data.progress_checked_at
                      ? `Atualizado às ${new Intl.DateTimeFormat("pt-BR", {
                          hour: "2-digit",
                          minute: "2-digit",
                          timeZone: data.timezone,
                        }).format(new Date(data.progress_checked_at))} · ${data.progress_accounts ?? 0} conta(s)`
                      : "Ainda não medido hoje."}
              </p>
            </div>
          )}

          <form
            className="mt-6 grid gap-4 sm:grid-cols-2"
            onSubmit={(event) => {
              event.preventDefault();
              setFeedback(null);
              if (targetValid) save.mutate();
            }}
          >
            <label className="block">
              <span className="text-sm text-fg-2">Visualizações por dia</span>
              <input
                className="field mt-2"
                inputMode="numeric"
                min={1}
                onChange={(event) => setTarget(event.target.value.replace(/\D/g, ""))}
                placeholder="Ex.: 10000"
                required
                value={target}
              />
            </label>
            <label className="block">
              <span className="text-sm text-fg-2">Fuso horário do dia</span>
              <select className="field mt-2" onChange={(event) => setTimeZone(event.target.value)} value={timeZone}>
                {zoneOptions.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-3 sm:col-span-2">
              <input
                checked={enabled}
                className="size-4 accent-[#536dfe]"
                onChange={(event) => setEnabled(event.target.checked)}
                type="checkbox"
              />
              <span className="text-sm text-fg-2">Acompanhar esta meta</span>
            </label>
            <div className="sm:col-span-2">
              <button className="btn-primary w-full sm:w-auto" disabled={!targetValid || save.isPending} type="submit">
                {save.isPending ? "Salvando..." : "Salvar meta"}
              </button>
            </div>
          </form>
        </>
      )}

      <div className="mt-6 border-t border-line-soft pt-5">
        <h3 className="text-sm font-medium text-fg">Notificações neste dispositivo</h3>
        {availability === "ios-needs-install" ? (
          <p className="mt-2 text-sm leading-6 text-muted">
            No iPhone e iPad, adicione o FlashPost à Tela de Início (Compartilhar → Adicionar à Tela de
            Início), abra pelo ícone e ative aqui. Requer iOS 16.4 ou superior.
          </p>
        ) : availability !== "supported" ? (
          <p className="mt-2 text-sm leading-6 text-muted">
            Este navegador não oferece notificações push. Use Chrome, Edge, Firefox ou Safari atualizados.
          </p>
        ) : pushConfig.data && !pushConfig.data.supported ? (
          <p className="mt-2 text-sm leading-6 text-muted">
            O servidor ainda não está configurado para enviar notificações.
          </p>
        ) : (
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              className={subscribedHere ? "btn-secondary" : "btn-primary"}
              disabled={togglePush.isPending || subscribedHere === null || !pushConfig.data}
              onClick={() => togglePush.mutate()}
              type="button"
            >
              {subscribedHere ? <BellOff size={16} /> : <Bell size={16} />}
              {togglePush.isPending
                ? "Aguarde..."
                : subscribedHere
                  ? "Desativar neste dispositivo"
                  : "Ativar notificações"}
            </button>
            {subscribedHere && (
              <button
                className="btn-ghost"
                disabled={testPush.isPending}
                onClick={() => testPush.mutate()}
                type="button"
              >
                <Send size={15} />
                Enviar teste
              </button>
            )}
          </div>
        )}
        {pushConfig.data && pushConfig.data.devices > 0 && (
          <p className="mt-2 text-xs text-muted">
            {pushConfig.data.devices} dispositivo(s) recebendo avisos nesta conta.
          </p>
        )}
        <p className="mt-3 text-xs leading-5 text-muted">
          As visualizações vêm dos Insights da Meta, que podem atrasar até 48 horas. Você recebe no máximo um
          aviso por meta por dia.
        </p>
      </div>

      {feedback && (
        <p
          className={`mt-4 text-sm ${feedback.kind === "ok" ? "text-success" : "text-danger"}`}
          role={feedback.kind === "ok" ? "status" : "alert"}
        >
          {feedback.text}
        </p>
      )}
    </section>
  );
}
