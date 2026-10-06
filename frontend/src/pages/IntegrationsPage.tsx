import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, KeyRound, PlugZap, Plus, Save, Trash2 } from "lucide-react";

import { ErrorState, LoadingState } from "@/components/PageState";
import { ApiError, apiRequest } from "@/services/api";

type SmokepayOperation = {
  id: string;
  name: string;
  split_percent: string;
  is_active: boolean;
  webhook_url: string;
  created_at: string;
  updated_at: string;
};

type OperationsResponse = {
  operations: SmokepayOperation[];
};

function errorMessage(error: unknown): string | null {
  if (!error) return null;
  return error instanceof ApiError
    ? error.message
    : "Não foi possível concluir a operação.";
}

function notify(message: string) {
  window.dispatchEvent(new CustomEvent("flashpost-toast", { detail: message }));
}

export function IntegrationsPage() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [splitPercent, setSplitPercent] = useState("100");
  const [editValues, setEditValues] = useState<
    Record<string, { name: string; split_percent: string; is_active: boolean }>
  >({});
  const integrations = useQuery({
    queryKey: ["integrations", "smokepay"],
    queryFn: () =>
      apiRequest<OperationsResponse>("/api/integrations/smokepay"),
    retry: false,
  });
  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: ["integrations", "smokepay"] });
  const createOperation = useMutation({
    mutationFn: () =>
      apiRequest<SmokepayOperation>("/api/integrations/smokepay", {
        method: "POST",
        body: { name, split_percent: splitPercent },
      }),
    onSuccess: async () => {
      setName("");
      setSplitPercent("100");
      await refresh();
    },
  });
  const updateOperation = useMutation({
    mutationFn: (operation: SmokepayOperation) => {
      const values = editValues[operation.id] ?? {
        name: operation.name,
        split_percent: operation.split_percent,
        is_active: operation.is_active,
      };
      return apiRequest<SmokepayOperation>(
        `/api/integrations/smokepay/${operation.id}`,
        { method: "PUT", body: values },
      );
    },
    onSuccess: refresh,
  });
  const rotateKey = useMutation({
    mutationFn: (id: string) =>
      apiRequest<SmokepayOperation>(
        `/api/integrations/smokepay/${id}/rotate-key`,
        { method: "POST" },
      ),
    onSuccess: refresh,
  });
  const deleteOperation = useMutation({
    mutationFn: (id: string) =>
      apiRequest<void>(`/api/integrations/smokepay/${id}`, {
        method: "DELETE",
      }),
    onSuccess: refresh,
  });

  async function copyWebhookUrl(value: string) {
    try {
      await navigator.clipboard.writeText(value);
      notify("URL do webhook copiada.");
    } catch {
      notify("Não foi possível copiar a URL. Selecione e copie manualmente.");
    }
  }

  if (integrations.isLoading) {
    return <LoadingState label="Carregando integrações" />;
  }
  if (integrations.error || !integrations.data) {
    return (
      <ErrorState
        message={
          errorMessage(integrations.error) ??
          "Não foi possível carregar as integrações."
        }
      />
    );
  }

  const errors = [
    errorMessage(createOperation.error),
    errorMessage(updateOperation.error),
    errorMessage(rotateKey.error),
    errorMessage(deleteOperation.error),
  ].filter((message): message is string => Boolean(message));

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <header>
        <p className="text-xs font-medium uppercase tracking-[0.16em] text-[#8295ff]">
          Conexões externas
        </p>
        <h1 className="mt-2 flex items-center gap-2 text-2xl font-semibold text-[#f5f7fb] sm:text-3xl">
          <PlugZap className="text-[#8295ff]" size={25} />
          Integrações Smokepay
        </h1>
        <p className="mt-2 text-sm text-[#94a3b8]">
          Crie um endpoint por operação e configure a parte da venda que fica
          como faturamento líquido.
        </p>
      </header>

      {errors.map((error) => (
        <ErrorState key={error} message={error} />
      ))}

      <form
        className="dashboard-card grid gap-3 rounded-xl p-5 sm:grid-cols-[minmax(0,1fr)_160px_auto]"
        onSubmit={(event: FormEvent) => {
          event.preventDefault();
          createOperation.mutate();
        }}
      >
        <label className="grid gap-1.5 text-xs text-[#94a3b8]">
          Nome da operação
          <input
            className="collaborator-input"
            maxLength={120}
            onChange={(event) => setName(event.target.value)}
            placeholder="Ex.: Produto principal"
            required
            value={name}
          />
        </label>
        <label className="grid gap-1.5 text-xs text-[#94a3b8]">
          Split líquido (%)
          <input
            className="collaborator-input"
            max={100}
            min={0}
            onChange={(event) => setSplitPercent(event.target.value)}
            required
            step="0.01"
            type="number"
            value={splitPercent}
          />
        </label>
        <button
          className="inline-flex min-h-10 items-center justify-center gap-2 self-end rounded-lg bg-[#536dfe] px-4 text-sm font-semibold text-white disabled:opacity-50"
          disabled={createOperation.isPending}
          type="submit"
        >
          <Plus size={15} />
          {createOperation.isPending ? "Criando..." : "Criar webhook"}
        </button>
        <p className="text-xs text-[#78839b] sm:col-span-3">
          O padrão é 100%. Alterar o split só afeta vendas recebidas depois da
          alteração; cada venda salva sua própria taxa líquida.
        </p>
      </form>

      {integrations.data.operations.length === 0 ? (
        <section className="dashboard-card rounded-xl p-6 text-sm text-[#94a3b8]">
          Nenhuma operação cadastrada. Crie uma para gerar uma URL de webhook
          exclusiva.
        </section>
      ) : (
        <section aria-label="Operações Smokepay" className="space-y-3">
          {integrations.data.operations.map((operation) => {
            const values = editValues[operation.id] ?? {
              name: operation.name,
              split_percent: operation.split_percent,
              is_active: operation.is_active,
            };
            return (
              <article
                className="dashboard-card space-y-4 rounded-xl p-5"
                key={operation.id}
              >
                <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_160px_auto]">
                  <label className="grid gap-1.5 text-xs text-[#94a3b8]">
                    Operação
                    <input
                      className="collaborator-input"
                      maxLength={120}
                      onChange={(event) =>
                        setEditValues({
                          ...editValues,
                          [operation.id]: {
                            ...values,
                            name: event.target.value,
                          },
                        })
                      }
                      value={values.name}
                    />
                  </label>
                  <label className="grid gap-1.5 text-xs text-[#94a3b8]">
                    Split líquido (%)
                    <input
                      className="collaborator-input"
                      max={100}
                      min={0}
                      onChange={(event) =>
                        setEditValues({
                          ...editValues,
                          [operation.id]: {
                            ...values,
                            split_percent: event.target.value,
                          },
                        })
                      }
                      step="0.01"
                      type="number"
                      value={values.split_percent}
                    />
                  </label>
                  <button
                    className="inline-flex min-h-10 items-center justify-center gap-2 self-end rounded-lg border border-[#34446f] px-3 text-sm font-medium text-[#c3ccff] disabled:opacity-50"
                    disabled={updateOperation.isPending}
                    onClick={() => updateOperation.mutate(operation)}
                    type="button"
                  >
                    <Save size={14} />
                    Salvar
                  </button>
                  <label className="flex items-center gap-2 text-xs text-[#cbd5e1] sm:col-span-3">
                    <input
                      checked={values.is_active}
                      onChange={(event) =>
                        setEditValues({
                          ...editValues,
                          [operation.id]: {
                            ...values,
                            is_active: event.target.checked,
                          },
                        })
                      }
                      type="checkbox"
                    />
                    Webhook ativo
                  </label>
                </div>

                <div className="rounded-lg border border-[#27334a] bg-[#090c11] p-3">
                  <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-[#8295ff]">
                    URL para cadastrar na Smokepay
                  </p>
                  <div className="flex flex-wrap items-center gap-2">
                    <code className="min-w-0 flex-1 break-all text-xs text-[#cbd5e1]">
                      {operation.webhook_url}
                    </code>
                    <button
                      aria-label={`Copiar URL de ${operation.name}`}
                      className="inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-[#34446f] px-3 text-xs text-[#c3ccff]"
                      onClick={() => void copyWebhookUrl(operation.webhook_url)}
                      type="button"
                    >
                      <Copy size={13} />
                      Copiar
                    </button>
                  </div>
                  <p className="mt-2 text-[10px] text-[#78839b]">
                    Trate esta URL como uma credencial: qualquer pessoa que a
                    possua pode enviar eventos para esta operação.
                  </p>
                </div>

                <div className="flex flex-wrap gap-2">
                  <button
                    className="inline-flex min-h-9 items-center gap-2 rounded-lg border border-[#51422b] px-3 text-xs font-medium text-[#f2d48a] disabled:opacity-50"
                    disabled={rotateKey.isPending}
                    onClick={() => {
                      if (
                        window.confirm(
                          "Gerar uma nova URL invalidará a URL anterior configurada na Smokepay. Continuar?",
                        )
                      ) {
                        rotateKey.mutate(operation.id);
                      }
                    }}
                    type="button"
                  >
                    <KeyRound size={13} />
                    Renovar URL
                  </button>
                  <button
                    className="inline-flex min-h-9 items-center gap-2 rounded-lg border border-[#63343b] px-3 text-xs font-medium text-[#f1a3ad] disabled:opacity-50"
                    disabled={deleteOperation.isPending}
                    onClick={() => {
                      if (
                        window.confirm(
                          `Excluir "${operation.name}"? As vendas existentes serão preservadas, mas deixarão de aparecer nesta operação.`,
                        )
                      ) {
                        deleteOperation.mutate(operation.id);
                      }
                    }}
                    type="button"
                  >
                    <Trash2 size={13} />
                    Excluir
                  </button>
                </div>
              </article>
            );
          })}
        </section>
      )}
    </div>
  );
}
