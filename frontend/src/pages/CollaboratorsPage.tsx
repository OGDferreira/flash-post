import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BarChart3,
  CircleDollarSign,
  LockKeyhole,
  Medal,
  Plus,
  Save,
  Trash2,
  UnlockKeyhole,
  UsersRound,
} from "lucide-react";

import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { ApiError, apiRequest, type CollaboratorReport } from "@/services/api";

type CollaboratorsResponse = {
  collaborators: CollaboratorReport[];
  owner_connections_today: number;
  team_connections_today: number;
};

type CollaboratorRankingResponse = {
  month: string;
  total_connections: number;
  collaborators: {
    user_id: string;
    full_name: string;
    nickname: string;
    connections: number;
    position: number;
  }[];
};

type CollaboratorDraft = {
  rate_per_connection: number;
  daily_connection_goal: number;
  monthly_connection_goal: number;
  monthly_bonus: number;
};

type CollaboratorUpdateDraft = CollaboratorDraft & {
  apply_rate_to_existing_accounts: boolean;
};

type WorkDaysResponse = {
  month: string;
  daily_rate: number;
  total_amount: number;
  days: { day: string; amount: number; paid: boolean }[];
};

type NewCollaboratorForm = CollaboratorDraft & {
  full_name: string;
  nickname: string;
  email: string;
  password: string;
};

const blankForm: NewCollaboratorForm = {
  full_name: "",
  nickname: "",
  email: "",
  password: "",
  rate_per_connection: 0,
  daily_connection_goal: 0,
  monthly_connection_goal: 0,
  monthly_bonus: 0,
};

function money(value: number) {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(value);
}

function formatConnectionDate(value: string | null) {
  if (!value) return "Data indisponível";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "America/Sao_Paulo",
  }).format(new Date(value));
}

function displayError(error: unknown, fallback: string) {
  return error instanceof ApiError ? error.message : error ? fallback : null;
}

function draftFrom(item: CollaboratorReport): CollaboratorUpdateDraft {
  return {
    rate_per_connection: item.rate_per_connection,
    daily_connection_goal: item.daily_connection_goal,
    monthly_connection_goal: item.monthly_connection_goal,
    monthly_bonus: item.monthly_bonus,
    apply_rate_to_existing_accounts: false,
  };
}

export function CollaboratorsPage() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(blankForm);
  const [drafts, setDrafts] = useState<Record<string, CollaboratorUpdateDraft>>({});
  const report = useQuery({
    queryKey: ["collaborators", "report"],
    queryFn: () => apiRequest<CollaboratorsResponse>("/api/collaborators"),
    refetchInterval: 30_000,
    retry: false,
  });
  const ranking = useQuery({
    queryKey: ["collaborators", "ranking"],
    queryFn: () => apiRequest<CollaboratorRankingResponse>("/api/collaborators/ranking"),
    refetchInterval: 60_000,
    retry: false,
  });
  const create = useMutation({
    mutationFn: () =>
      apiRequest<CollaboratorsResponse>("/api/collaborators", {
        method: "POST",
        body: form,
      }),
    onSuccess: async () => {
      setForm(blankForm);
      await queryClient.invalidateQueries({ queryKey: ["collaborators"] });
    },
  });
  const update = useMutation({
    mutationFn: ({ memberId, values }: { memberId: string; values: CollaboratorUpdateDraft }) =>
      apiRequest<CollaboratorReport>(`/api/collaborators/${memberId}`, {
        method: "PATCH",
        body: values,
      }),
    onSuccess: async (_result, { memberId, values }) => {
      setDrafts((current) => ({
        ...current,
        [memberId]: { ...values, apply_rate_to_existing_accounts: false },
      }));
      await queryClient.invalidateQueries({ queryKey: ["collaborators"] });
    },
  });
  const payout = useMutation({
    mutationFn: (memberId: string) =>
      apiRequest(`/api/collaborators/${memberId}/payout`, { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["collaborators"] }),
  });
  const accessToggle = useMutation({
    mutationFn: ({ memberId, enabled }: { memberId: string; enabled: boolean }) =>
      apiRequest<CollaboratorReport>(`/api/collaborators/${memberId}/access`, {
        method: "PATCH",
        body: { enabled },
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["collaborators"] }),
  });
  const removeCollaborator = useMutation({
    mutationFn: (memberId: string) =>
      apiRequest<void>(`/api/collaborators/${memberId}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["collaborators"] }),
  });

  if (report.isLoading) return <LoadingState label="Carregando colaboradores" />;
  if (report.error || !report.data) {
    return <ErrorState message="Não foi possível carregar a equipe deste workspace." />;
  }

  const createError = displayError(create.error, "Não foi possível criar o colaborador.");
  const saveError = displayError(update.error, "Não foi possível salvar as configurações.");
  const payoutError = displayError(payout.error, "Não foi possível registrar o pagamento.");
  const accessError = displayError(
    accessToggle.error,
    "Não foi possível alterar o acesso do colaborador.",
  );
  const removeError = displayError(
    removeCollaborator.error,
    "Não foi possível excluir o colaborador.",
  );

  return (
    <div className="mx-auto max-w-[1320px] space-y-7">
      <header>
        <p className="text-xs font-medium uppercase tracking-[0.16em] text-[#8295ff]">
          Workspace
        </p>
        <h1 className="mt-2 text-2xl font-semibold text-[#f5f7fb] sm:text-3xl">
          Gestão de colaboradores
        </h1>
        <p className="mt-2 text-sm text-[#94a3b8]">
          Gerencie acessos, metas, remuneração e os pagamentos registrados para a equipe.
        </p>
      </header>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <article className="dashboard-card rounded-xl p-5">
          <p className="text-xs text-[#94a3b8]">Conexões feitas por você hoje</p>
          <p className="mt-2 text-3xl font-semibold text-[#f5f7fb]">
            {report.data.owner_connections_today}
          </p>
        </article>
        <article className="dashboard-card rounded-xl p-5">
          <p className="text-xs text-[#94a3b8]">Conexões da equipe hoje</p>
          <p className="mt-2 text-3xl font-semibold text-[#aab7ff]">
            {report.data.team_connections_today}
          </p>
        </article>
        <article className="dashboard-card rounded-xl p-5 sm:col-span-2 lg:col-span-1">
          <div className="flex items-center gap-2">
            <Medal className="text-[#f2d48a]" size={16} />
            <h2 className="text-xs font-semibold text-[#edf0f8]">Ranking mensal da equipe</h2>
          </div>
          {ranking.isLoading ? (
            <p className="mt-3 text-xs text-[#94a3b8]">Carregando ranking...</p>
          ) : ranking.error ? (
            <p className="mt-3 text-xs text-[#f1a3ad]">Não foi possível carregar o ranking.</p>
          ) : ranking.data?.collaborators.length ? (
            <ol className="mt-3 max-h-52 space-y-1.5 overflow-y-auto pr-1">
              {ranking.data.collaborators.map((person) => (
                <li className="flex items-center justify-between gap-3 text-xs" key={person.user_id}>
                  <span className="min-w-0 truncate text-[#cbd5e1]">
                    <strong className="mr-2 text-[#f2d48a]">#{person.position}</strong>
                    @{person.nickname}
                  </span>
                  <strong className="shrink-0 text-[#f5f7fb]">
                    {person.connections} {person.connections === 1 ? "conta" : "contas"}
                  </strong>
                </li>
              ))}
            </ol>
          ) : (
            <p className="mt-3 text-xs text-[#94a3b8]">Ainda não há conexões neste mês.</p>
          )}
        </article>
      </section>

      <section className="dashboard-card rounded-xl p-5 sm:p-6">
        <div className="mb-5 flex items-center gap-2">
          <Plus className="text-[#8295ff]" size={17} />
          <h2 className="text-sm font-semibold text-[#edf0f8]">Criar acesso de colaborador</h2>
        </div>
        <form
          className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"
          onSubmit={(event) => {
            event.preventDefault();
            create.mutate();
          }}
        >
          <Field label="Nome completo">
            <input
              autoComplete="name"
              className="collaborator-input"
              onChange={(event) => setForm({ ...form, full_name: event.target.value })}
              required
              value={form.full_name}
            />
          </Field>
          <Field label="Apelido">
            <input
              className="collaborator-input"
              onChange={(event) => setForm({ ...form, nickname: event.target.value })}
              required
              value={form.nickname}
            />
          </Field>
          <Field label="E-mail de login">
            <input
              autoComplete="email"
              className="collaborator-input"
              onChange={(event) => setForm({ ...form, email: event.target.value })}
              required
              type="email"
              value={form.email}
            />
          </Field>
          <Field label="Palavra-passe inicial">
            <input
              autoComplete="new-password"
              className="collaborator-input"
              minLength={8}
              onChange={(event) => setForm({ ...form, password: event.target.value })}
              required
              type="password"
              value={form.password}
            />
          </Field>
          <MoneyField
            label="Valor por conexão (R$)"
            onChange={(rate_per_connection) => setForm({ ...form, rate_per_connection })}
            value={form.rate_per_connection}
          />
          <NumberField
            label="Meta diária de conexões"
            onChange={(daily_connection_goal) => setForm({ ...form, daily_connection_goal })}
            value={form.daily_connection_goal}
          />
          <NumberField
            label="Meta mensal de conexões"
            onChange={(monthly_connection_goal) =>
              setForm({ ...form, monthly_connection_goal })
            }
            value={form.monthly_connection_goal}
          />
          <MoneyField
            label="Bónus ao cumprir meta mensal (R$)"
            onChange={(monthly_bonus) => setForm({ ...form, monthly_bonus })}
            value={form.monthly_bonus}
          />
          {createError && (
            <p className="text-sm text-[#f1a3ad] sm:col-span-2 xl:col-span-4" role="alert">
              {createError}
            </p>
          )}
          <div className="sm:col-span-2 xl:col-span-4">
            <button
              className="inline-flex min-h-10 items-center gap-2 rounded-lg bg-[#586eff] px-4 text-sm font-semibold text-white hover:bg-[#7187ff] disabled:opacity-60"
              disabled={create.isPending}
              type="submit"
            >
              <Plus size={15} />
              {create.isPending ? "Criando acesso..." : "Criar colaborador"}
            </button>
          </div>
        </form>
      </section>

      <section className="space-y-4">
        <div className="flex items-center gap-2">
          <UsersRound className="text-[#8295ff]" size={17} />
          <h2 className="text-sm font-semibold text-[#edf0f8]">
            Produção da equipe · hoje e mês atual
          </h2>
        </div>
        {saveError && <ErrorState message={saveError} />}
        {payoutError && <ErrorState message={payoutError} />}
        {accessError && <ErrorState message={accessError} />}
        {removeError && <ErrorState message={removeError} />}
        {report.data.collaborators.length === 0 ? (
          <EmptyState message="Ainda não há colaboradores neste workspace." />
        ) : (
          report.data.collaborators.map((item) => {
            const draft = drafts[item.member_id] ?? draftFrom(item);
            const maxDaily = Math.max(1, ...item.recent_days);
            return (
              <article className="dashboard-card space-y-5 rounded-xl p-5" key={item.member_id}>
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <h3 className="font-semibold text-[#f5f7fb]">{item.full_name}</h3>
                    <p className="mt-1 text-xs text-[#8295ff]">
                      @{item.nickname} · {item.email}
                    </p>
                    <span
                      className={`mt-2 inline-flex rounded-full border px-2 py-1 text-[10px] font-medium ${
                        item.access_status === "ACTIVE"
                          ? "border-[#315843] bg-[#10231a] text-[#a9e5c0]"
                          : "border-[#5a3037] bg-[#241216] text-[#f1a3ad]"
                      }`}
                    >
                      {item.access_status === "ACTIVE" ? "Acesso liberado" : "Acesso bloqueado"}
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      className={`inline-flex min-h-10 items-center gap-2 rounded-lg border px-3 text-xs font-semibold disabled:opacity-50 ${
                        item.access_status === "ACTIVE"
                          ? "border-[#5a3037] text-[#f1a3ad] hover:bg-[#241216]"
                          : "border-[#315843] text-[#a9e5c0] hover:bg-[#10231a]"
                      }`}
                      disabled={accessToggle.isPending}
                      onClick={() => {
                        const enabled = item.access_status !== "ACTIVE";
                        const action = enabled ? "liberar" : "bloquear";
                        if (
                          window.confirm(
                            `Deseja ${action} o acesso de ${item.full_name}? ${enabled ? "O colaborador poderá voltar a entrar neste workspace." : "Ele perderá acesso ao workspace imediatamente; seus dados e resultados serão preservados."}`,
                          )
                        ) {
                          accessToggle.mutate({ memberId: item.member_id, enabled });
                        }
                      }}
                      type="button"
                    >
                      {item.access_status === "ACTIVE" ? (
                        <LockKeyhole size={14} />
                      ) : (
                        <UnlockKeyhole size={14} />
                      )}
                      {item.access_status === "ACTIVE" ? "Bloquear acesso" : "Liberar acesso"}
                    </button>
                    <button
                      className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-[#5a3037] px-3 text-xs font-semibold text-[#f1a3ad] hover:bg-[#241216] disabled:opacity-50"
                      disabled={removeCollaborator.isPending}
                      onClick={() => {
                        if (
                          window.confirm(
                            `Excluir ${item.full_name} deste workspace? Os dados de pagamento e dias registrados serão removidos; as contas conectadas serão preservadas.`,
                          )
                        ) {
                          removeCollaborator.mutate(item.member_id);
                        }
                      }}
                      type="button"
                    >
                      <Trash2 size={14} />
                      Excluir colaborador
                    </button>
                    <div className="flex items-center gap-2 rounded-lg border border-[#27334a] bg-[#090b0e] px-3 py-2 text-xs">
                      <CircleDollarSign className="text-[#f2d48a]" size={15} />
                      <span className="text-[#94a3b8]">Devido</span>
                      <strong className="text-[#f2d48a]">{money(item.due_month)}</strong>
                    </div>
                  </div>
                </div>

                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
                  <SummaryMetric
                    label="Colaborador desde"
                    value={new Intl.DateTimeFormat("pt-BR", {
                      day: "2-digit",
                      month: "2-digit",
                      year: "numeric",
                      timeZone: "America/Sao_Paulo",
                    }).format(new Date(item.membership_started_at))}
                  />
                  <SummaryMetric label="Conexões hoje" value={String(item.connections_today)} />
                  <SummaryMetric label="Conexões no mês" value={String(item.connections_month)} />
                  <SummaryMetric label="Ganho do dia" value={money(item.earnings_today)} />
                  <SummaryMetric label="Pago no mês" value={money(item.paid_month)} />
                </div>

                <div className="rounded-lg border border-[#252c3e] bg-[#0a0d13] p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                    <span className="font-medium text-[#cbd5e1]">Meta mensal de conexões</span>
                    <span className="text-[#aab7ff]">
                      {item.connections_month} / {item.monthly_connection_goal || "—"} contas
                      {item.monthly_connection_goal > 0
                        ? ` · ${Math.min(
                            Math.round(
                              (item.connections_month / item.monthly_connection_goal) * 100,
                            ),
                            100,
                          )}%`
                        : ""}
                    </span>
                  </div>
                  {item.monthly_connection_goal > 0 ? (
                    <div
                      aria-label={`${item.connections_month} de ${item.monthly_connection_goal} contas da meta mensal`}
                      className="mt-3 h-2 overflow-hidden rounded-full bg-[#202838]"
                      role="progressbar"
                      aria-valuemin={0}
                      aria-valuemax={item.monthly_connection_goal}
                      aria-valuenow={Math.min(
                        item.connections_month,
                        item.monthly_connection_goal,
                      )}
                    >
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-[#536dfe] to-[#b171ff]"
                        style={{
                          width: `${Math.min(
                            (item.connections_month / item.monthly_connection_goal) * 100,
                            100,
                          )}%`,
                        }}
                      />
                    </div>
                  ) : (
                    <p className="mt-2 text-xs text-[#78839b]">
                      Ainda não há uma meta mensal definida.
                    </p>
                  )}
                </div>

                <div className="grid gap-4 lg:grid-cols-[1fr_1.1fr]">
                  <div className="rounded-lg border border-[#252c3e] bg-[#0a0d13] p-4">
                    <div className="mb-3 flex items-center gap-2 text-xs text-[#b7bfd0]">
                      <BarChart3 className="text-[#8295ff]" size={15} />
                      Conexões por dia · últimos 7 dias
                    </div>
                    <div className="flex h-20 items-end gap-2">
                      {item.recent_days.map((count, index) => (
                        <div className="flex h-full flex-1 flex-col justify-end gap-1" key={index}>
                          <span className="text-center text-[10px] text-[#78839b]">{count}</span>
                          <div
                            className="min-h-1 rounded-t bg-gradient-to-t from-[#536dfe] to-[#b171ff]"
                            style={{ height: `${Math.max(4, (count / maxDaily) * 58)}px` }}
                          />
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <MoneyField
                      label="Valor para novas conexões (R$)"
                      onChange={(value) =>
                        setDrafts({ ...drafts, [item.member_id]: { ...draft, rate_per_connection: value } })
                      }
                      value={draft.rate_per_connection}
                    />
                    <p className="text-xs leading-5 text-[#78839b] sm:col-span-2">
                      Ao alterar o valor, você poderá escolher se ele também vale para as contas já conectadas.
                    </p>
                    <NumberField
                      label="Meta diária"
                      onChange={(value) =>
                        setDrafts({ ...drafts, [item.member_id]: { ...draft, daily_connection_goal: value } })
                      }
                      value={draft.daily_connection_goal}
                    />
                    <NumberField
                      label="Meta mensal"
                      onChange={(value) =>
                        setDrafts({
                          ...drafts,
                          [item.member_id]: { ...draft, monthly_connection_goal: value },
                        })
                      }
                      value={draft.monthly_connection_goal}
                    />
                    <MoneyField
                      label="Bónus mensal (R$)"
                      onChange={(value) =>
                        setDrafts({ ...drafts, [item.member_id]: { ...draft, monthly_bonus: value } })
                      }
                      value={draft.monthly_bonus}
                    />
                    <div className="flex flex-wrap items-end gap-2 sm:col-span-2">
                      <button
                        className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-[#34446f] px-3 text-xs font-semibold text-[#c3ccff] hover:bg-[#151b2d] disabled:opacity-50"
                        disabled={update.isPending}
                        onClick={() => {
                          const applyRateToExistingAccounts =
                            draft.rate_per_connection !== item.rate_per_connection &&
                            window.confirm(
                              "Aplicar este valor também a todas as contas já conectadas?\n\nOK: atualizar as contas já conectadas.\nCancelar: aplicar somente às próximas conexões.",
                            );
                          update.mutate({
                            memberId: item.member_id,
                            values: {
                              ...draft,
                              apply_rate_to_existing_accounts: applyRateToExistingAccounts,
                            },
                          });
                        }}
                        type="button"
                      >
                        <Save size={14} />
                        Guardar metas e valores
                      </button>
                      <button
                        className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-[#315843] px-3 text-xs font-semibold text-[#a9e5c0] hover:bg-[#10231a] disabled:opacity-50"
                        disabled={payout.isPending || item.due_month <= 0}
                        onClick={() => {
                          if (window.confirm(`Registrar pagamento de ${money(item.due_month)} para ${item.full_name}?`)) {
                            payout.mutate(item.member_id);
                          }
                        }}
                        type="button"
                      >
                        Registrar pagamento do saldo
                      </button>
                      <span className="text-xs text-[#78839b]">
                        Projeção na meta: {money(item.projected_month)}
                      </span>
                    </div>
                  </div>
                </div>

                <WorkDaysPanel memberId={item.member_id} collaboratorName={item.full_name} />

                <details className="border-t border-[#202838] pt-4">
                  <summary className="cursor-pointer list-none text-xs font-medium text-[#cbd5e1] marker:hidden">
                    <span className="inline-flex items-center gap-2">
                      <UsersRound className="text-[#8295ff]" size={14} />
                      Contas vinculadas e valores salvos
                      <span className="rounded-full border border-[#27334a] px-2 py-0.5 text-[10px] text-[#94a3b8]">
                        {item.account_earnings.length}
                      </span>
                    </span>
                  </summary>
                  <div className="mt-3 space-y-2">
                    {item.account_earnings.length ? (
                    <div className="overflow-x-auto">
                      <table className="w-full min-w-[420px] text-left text-xs">
                        <thead className="text-[#78839b]">
                          <tr>
                            <th className="py-2 pr-3 font-medium">Conta</th>
                            <th className="py-2 pr-3 font-medium">Conectada em</th>
                            <th className="py-2 text-right font-medium">Valor salvo</th>
                          </tr>
                        </thead>
                        <tbody>
                          {item.account_earnings.map((account) => (
                            <tr className="border-t border-[#202838]" key={account.account_id}>
                              <td className="py-2 pr-3 text-[#e6eaf2]">@{account.username}</td>
                              <td className="py-2 pr-3 text-[#94a3b8]">
                                {formatConnectionDate(account.connected_at)}
                              </td>
                              <td className="py-2 text-right font-medium text-[#f2d48a]">
                                {money(account.rate_per_connection)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className="text-xs text-[#78839b]">
                      O valor atual será salvo quando uma nova conta for conectada.
                    </p>
                  )}
                  <p className="text-xs text-[#78839b]">
                    Ao salvar um novo valor, ele passa a valer para conexões futuras; os valores já salvos não mudam.
                  </p>
                  </div>
                </details>
              </article>
            );
          })
        )}
      </section>
    </div>
  );
}

function WorkDaysPanel({
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
    <section className="rounded-lg border border-[#252c3e] bg-[#0a0d13] p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h4 className="text-sm font-medium text-[#e6eaf2]">Dias trabalhados · {collaboratorName}</h4>
          <p className="mt-1 text-xs text-[#78839b]">
            Cada dia selecionado vale a taxa atual por conta conectada: {money(workDays.data?.daily_rate ?? 0)}.
          </p>
        </div>
        <label className="flex items-center gap-2 text-xs text-[#94a3b8]">
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
        <p className="mt-4 text-xs text-[#78839b]">Carregando dias...</p>
      ) : workDays.error ? (
        <p className="mt-4 text-xs text-[#f1a3ad]">Não foi possível carregar os dias trabalhados.</p>
      ) : (
        <>
          <div className="mt-4 grid grid-cols-7 gap-1 text-center">
            {["D", "S", "T", "Q", "Q", "S", "S"].map((label, index) => (
              <span className="py-1 text-[10px] text-[#64748b]" key={`${label}-${index}`}>
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
                      ? "border-[#315843] bg-[#10231a] text-[#a9e5c0]"
                      : workDay
                        ? "border-[#536dfe] bg-[#151b2d] text-[#d5dcff]"
                        : "border-[#202838] text-[#94a3b8] hover:bg-[#171e31]"
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
                      ? `${date}: pago`
                      : workDay
                        ? `${date}: selecionado, ${money(workDay.amount)}`
                        : isFuture
                          ? "Dia futuro"
                          : "Marcar como trabalhado"
                  }
                  type="button"
                >
                  {index + 1}
                </button>
              );
            })}
          </div>
          {saveDays.error && (
            <p className="mt-3 text-xs text-[#f1a3ad]">
              {displayError(saveDays.error, "Não foi possível salvar os dias trabalhados.")}
            </p>
          )}
          <div className="mt-4 flex flex-wrap justify-between gap-2 border-t border-[#202838] pt-3 text-xs">
            <span className="text-[#94a3b8]">
              {selectedDays.length} dia(s) marcado(s)
              {selectedDays.some((item) => item.paid) && " · verde = pago"}
            </span>
            <strong className="text-[#f2d48a]">
              Total dos dias: {money(workDays.data?.total_amount ?? 0)}
            </strong>
          </div>
        </>
      )}
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="grid gap-1.5 text-xs text-[#94a3b8]">
      {label}
      {children}
    </label>
  );
}

function MoneyField({
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

function NumberField({
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

function SummaryMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-[#252c3e] bg-[#0a0d13] p-3">
      <p className="text-[10px] uppercase tracking-[0.1em] text-[#78839b]">{label}</p>
      <p className="mt-1 text-lg font-semibold text-[#e8ebf4]">{value}</p>
    </div>
  );
}
