import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type WorkDaysResponse, money, displayError } from "@/pages/collaborators/collaboratorShared";

import { apiRequest } from "@/services/api";

export function WorkDaysPanel({
  memberId,
  collaboratorName,
}: {
  memberId: string;
  collaboratorName: string;
}) {
  const queryClient = useQueryClient();
  const currentMonth = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Sao_Paulo",
    year: "numeric",
    month: "2-digit",
  }).format(new Date());
  const [month, setMonth] = useState(currentMonth);
  const workDays = useQuery({
    queryKey: ["collaborators", memberId, "work-days", month],
    queryFn: () =>
      apiRequest<WorkDaysResponse>(
        `/api/collaborators/${memberId}/work-days?month=${month}`,
      ),
  });
  const saveDays = useMutation({
    mutationFn: (days: string[]) =>
      apiRequest<WorkDaysResponse>(
        `/api/collaborators/${memberId}/work-days?month=${month}`,
        { method: "PUT", body: { days } },
      ),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: ["collaborators", memberId, "work-days"],
        }),
        queryClient.invalidateQueries({ queryKey: ["collaborators"] }),
      ]);
    },
  });
  const [year, monthNumber] = month.split("-").map(Number);
  const firstWeekday = new Date(year, monthNumber - 1, 1).getDay();
  const dayCount = new Date(year, monthNumber, 0).getDate();
  const localToday = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Sao_Paulo",
  }).format(new Date());
  const selectedDays = workDays.data?.days ?? [];
  const daysByDate = new Map(selectedDays.map((item) => [item.day, item]));

  return (
    <section className="rounded-lg border border-line bg-surface-inset p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h4 className="text-sm font-medium text-fg">Dias trabalhados · {collaboratorName}</h4>
          <p className="mt-1 text-xs text-muted">
            Os dias agrupam o valor das contas conectadas (não acrescentam uma diária). Cada conta usa seu valor salvo.
          </p>
        </div>
        <label className="flex items-center gap-2 text-xs text-muted">
          Mês
          <input
            aria-label={`Mês dos dias trabalhados de ${collaboratorName}`}
            className="collaborator-input w-auto"
            max={currentMonth}
            onChange={(event) => setMonth(event.target.value)}
            type="month"
            value={month}
          />
        </label>
      </div>
      {workDays.isLoading ? (
        <p className="mt-4 text-xs text-muted">Carregando dias...</p>
      ) : workDays.error ? (
        <p className="mt-4 text-xs text-danger">Não foi possível carregar os dias trabalhados.</p>
      ) : (
        <>
          <div className="mt-4 grid grid-cols-7 gap-1 text-center">
            {["D", "S", "T", "Q", "Q", "S", "S"].map((label, index) => (
              <span className="py-1 text-[10px] text-muted" key={`${label}-${index}`}>
                {label}
              </span>
            ))}
            {Array.from({ length: firstWeekday }, (_, index) => (
              <span aria-hidden="true" key={`blank-${index}`} />
            ))}
            {Array.from({ length: dayCount }, (_, index) => {
              const date = `${month}-${String(index + 1).padStart(2, "0")}`;
              const workDay = daysByDate.get(date);
              const isFuture = date > localToday;
              return (
                <button
                  aria-pressed={Boolean(workDay)}
                  className={`min-h-9 rounded-md border text-xs disabled:cursor-not-allowed disabled:opacity-45 ${
                    workDay?.paid
                      ? "border-success/30 bg-success-soft text-success"
                      : workDay
                        ? "border-brand bg-brand-soft text-accent"
                        : "border-line-soft text-muted hover:bg-brand-soft"
                  }`}
                  disabled={isFuture || workDay?.paid || saveDays.isPending}
                  key={date}
                  onClick={() => {
                    const nextDays = selectedDays
                      .filter((item) => !item.paid && item.day !== date)
                      .map((item) => item.day);
                    if (!workDay) nextDays.push(date);
                    saveDays.mutate(nextDays);
                  }}
                  title={
                    workDay?.paid
                      ? `${date}: ${workDay.connections} conta(s), ${money(workDay.amount)}, pago`
                      : workDay
                        ? `${date}: ${workDay.connections} conta(s), ${money(workDay.amount)}`
                        : isFuture
                          ? "Dia futuro"
                          : "Marcar como trabalhado"
                  }
                  type="button"
                >
                  <span className="flex flex-col items-center leading-tight">
                    <span>{index + 1}</span>
                    {workDay && (
                      <span className="mt-0.5 text-[9px] text-accent">
                        {workDay.connections}
                      </span>
                    )}
                  </span>
                </button>
              );
            })}
          </div>
          {saveDays.error && (
            <p className="mt-3 text-xs text-danger">
              {displayError(saveDays.error, "Não foi possível salvar os dias trabalhados.")}
            </p>
          )}
          <div className="mt-4 flex flex-wrap justify-between gap-2 border-t border-line-soft pt-3 text-xs">
            <span className="text-muted">
              {selectedDays.length} dia(s) marcado(s) · {workDays.data?.total_connections ?? 0} conta(s)
              {selectedDays.some((item) => item.paid) && " · verde = pago"}
            </span>
            <strong className="text-warning">
              Total dos dias: {money(workDays.data?.total_amount ?? 0)}
            </strong>
          </div>
        </>
      )}
    </section>
  );
}

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="grid gap-1.5 text-xs text-muted">
      {label}
      {children}
    </label>
  );
}

export function MoneyField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <Field label={label}>
      <input
        className="collaborator-input"
        min={0}
        onChange={(event) => onChange(Number(event.target.value))}
        step="0.01"
        type="number"
        value={value}
      />
    </Field>
  );
}

export function NumberField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <Field label={label}>
      <input
        className="collaborator-input"
        min={0}
        onChange={(event) => onChange(Number(event.target.value))}
        step={1}
        type="number"
        value={value}
      />
    </Field>
  );
}

export function SummaryMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-line bg-surface-inset p-3">
      <p className="text-[10px] uppercase tracking-[0.1em] text-muted">{label}</p>
      <p className="mt-1 text-lg font-semibold text-fg">{value}</p>
    </div>
  );
}
