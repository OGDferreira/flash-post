import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Target } from "lucide-react";

import type { DailyViewsGoal } from "@/components/DailyViewsGoalCard";
import { ApiError, apiRequest } from "@/services/api";

const numberFormat = new Intl.NumberFormat("pt-BR");

/** Owner view: daily views goal of every active member, editable inline. */
export function MemberGoalsPanel() {
  const queryClient = useQueryClient();
  const goals = useQuery({
    queryKey: ["notifications", "goals"],
    queryFn: () => apiRequest<{ goals: DailyViewsGoal[] }>("/api/notifications/goals"),
    staleTime: 60_000,
    refetchInterval: 5 * 60_000,
  });
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const save = useMutation({
    mutationFn: ({ goal, target }: { goal: DailyViewsGoal; target: number }) =>
      apiRequest<DailyViewsGoal>(`/api/notifications/goals/${goal.user_id}`, {
        method: "PUT",
        body: { target_views: target, enabled: true, timezone: goal.timezone },
      }),
    onSuccess: (_data, { goal }) => {
      setDrafts(({ [goal.user_id]: _removed, ...rest }) => rest);
      void queryClient.invalidateQueries({ queryKey: ["notifications", "goals"] });
      void queryClient.invalidateQueries({ queryKey: ["notifications", "goal", "me"] });
    },
  });

  return (
    <section className="glass-panel p-4" aria-labelledby="member-goals-title">
      <h2 id="member-goals-title" className="flex items-center gap-2 text-base font-semibold text-[#f5f7fb]">
        <Target size={16} className="text-[#8295ff]" />
        Metas diárias de visualizações
      </h2>
      <p className="mt-1 text-sm text-[#94a3b8]">
        Colaboradores são medidos nas contas que conectaram; o responsável, em todas as contas ativas.
      </p>
      {goals.isLoading ? (
        <div className="mt-4 space-y-2" aria-busy="true">
          <div className="skeleton h-12" />
          <div className="skeleton h-12" />
        </div>
      ) : goals.error ? (
        <p className="mt-4 text-sm text-[#f1a3ad]">Não foi possível carregar as metas.</p>
      ) : (
        <ul className="mt-4 divide-y divide-line-soft">
          {goals.data?.goals.map((goal) => {
            const draft = drafts[goal.user_id] ?? (goal.target_views ? String(goal.target_views) : "");
            const value = Number(draft);
            const changed = draft !== (goal.target_views ? String(goal.target_views) : "");
            return (
              <li className="flex flex-wrap items-center gap-3 py-3" key={goal.user_id}>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-[#e6eaf2]">
                    {goal.full_name ?? "Membro"}
                    <span className="ml-2 text-xs font-normal text-[#64748b]">
                      {goal.role === "OWNER" ? "Responsável" : "Colaborador"}
                    </span>
                  </p>
                  <p className="mt-0.5 text-xs text-[#94a3b8]">
                    {!goal.configured
                      ? "Sem meta"
                      : goal.progress_views === null
                        ? `Hoje: — de ${numberFormat.format(goal.target_views ?? 0)}`
                        : `Hoje: ${numberFormat.format(goal.progress_views)} de ${numberFormat.format(goal.target_views ?? 0)}`}
                    {goal.notified_today && " · atingida"}
                  </p>
                </div>
                <form
                  className="flex items-center gap-2"
                  onSubmit={(event) => {
                    event.preventDefault();
                    if (Number.isInteger(value) && value >= 1) save.mutate({ goal, target: value });
                  }}
                >
                  <input
                    aria-label={`Meta diária de ${goal.full_name ?? "membro"}`}
                    className="field !min-h-10 w-32"
                    inputMode="numeric"
                    onChange={(event) =>
                      setDrafts((current) => ({
                        ...current,
                        [goal.user_id]: event.target.value.replace(/\D/g, ""),
                      }))
                    }
                    placeholder="Meta"
                    value={draft}
                  />
                  <button
                    className="btn-secondary !min-h-10"
                    disabled={!changed || !(value >= 1) || save.isPending}
                    type="submit"
                  >
                    Salvar
                  </button>
                </form>
              </li>
            );
          })}
        </ul>
      )}
      {save.error && (
        <p className="mt-3 text-sm text-[#f1a3ad]" role="alert">
          {save.error instanceof ApiError ? save.error.message : "Não foi possível salvar a meta."}
        </p>
      )}
    </section>
  );
}
