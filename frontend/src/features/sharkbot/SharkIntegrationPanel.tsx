import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy } from "lucide-react";

import { ErrorState, LoadingState } from "@/components/PageState";
import { SharkAccountsPanel } from "@/features/sharkbot/SharkAccountsPanel";
import { ApiError, apiRequest } from "@/services/api";

type SharkbotWebhookSettings = {
  webhook_url: string;
  account_webhooks: { account_id: string; username: string; webhook_url: string }[];
};

/** Sharkbot webhook URLs and Shark accounts, shown next to the Smokepay ones. */
export function SharkIntegrationPanel() {
  const queryClient = useQueryClient();
  const [copyFeedback, setCopyFeedback] = useState<string | null>(null);
  const settings = useQuery({
    queryKey: ["sharkbot", "webhook-settings"],
    queryFn: () => apiRequest<SharkbotWebhookSettings>("/api/sharkbot/webhook/config"),
    retry: false,
  });
  const rotateSharkbotWebhook = useMutation({
    mutationFn: () =>
      apiRequest<SharkbotWebhookSettings>("/api/sharkbot/webhook/rotate", {
        method: "POST",
      }),
    onSuccess: (settings) => {
      queryClient.setQueryData(["sharkbot", "webhook-settings"], settings);
      setCopyFeedback("URL renovada. Atualize o endereço configurado no Sharkbot.");
    },
  });

  if (settings.isLoading) return <LoadingState label="Carregando Sharkbot" />;
  if (settings.error || !settings.data) {
    return (
      <ErrorState
        message={
          settings.error instanceof ApiError
            ? settings.error.message
            : "Não foi possível carregar a URL do webhook Sharkbot."
        }
        onRetry={() => void settings.refetch()}
      />
    );
  }

  return (
    <div className="space-y-5">
      {rotateSharkbotWebhook.error && (
        <ErrorState
          message={
            rotateSharkbotWebhook.error instanceof ApiError
              ? rotateSharkbotWebhook.error.message
              : "Não foi possível renovar a URL."
          }
        />
      )}
      <section className="space-y-4 rounded-xl border border-line bg-surface p-4 sm:p-5">
        <div>
          <h3 className="font-medium text-[#f5f7fb]">Integração Sharkbot</h3>
          <p className="mt-2 text-sm leading-6 text-[#94a3b8]">
            Uma única URL serve para todos os seus bots e fluxos do Sharkbot: as vendas são
            separadas pelo bot e pelo fluxo informados em cada evento e ficam restritas a este
            workspace. Reenvios do mesmo evento não duplicam leads nem vendas.
          </p>
        </div>
        <label className="grid gap-2 text-sm text-[#cbd5e1]">
          URL do webhook para cadastrar no Sharkbot
          <input
            className="min-h-11 rounded-lg border border-line bg-surface-inset px-3 font-mono text-xs text-[#cbd5e1] outline-none focus:border-[#7186ff]"
            readOnly
            value={settings.data.webhook_url}
          />
        </label>
        {copyFeedback && (
          <p className="text-sm text-[#9de0c0]" role="status">
            {copyFeedback}
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          <button
            className="inline-flex min-h-10 items-center gap-2 rounded-lg bg-[#536dfe] px-3 py-2 text-sm text-white disabled:opacity-60"
            type="button"
            onClick={() => {
              void navigator.clipboard
                .writeText(settings.data.webhook_url)
                .then(() => setCopyFeedback("URL copiada. Cole-a nas configurações do Sharkbot."))
                .catch(() =>
                  setCopyFeedback("Não foi possível copiar automaticamente. Selecione e copie a URL."),
                );
            }}
          >
            <Copy size={15} />
            Copiar URL
          </button>
          <button
            className="min-h-10 rounded-lg border border-[#47252d] px-3 py-2 text-sm text-[#f1a3ad] disabled:opacity-60"
            type="button"
            disabled={rotateSharkbotWebhook.isPending}
            onClick={() => {
              if (
                window.confirm(
                  "Gerar uma nova URL invalidará imediatamente a URL atual. Será necessário atualizá-la no Sharkbot. Continuar?",
                )
              ) {
                rotateSharkbotWebhook.mutate();
              }
            }}
          >
            {rotateSharkbotWebhook.isPending ? "Gerando..." : "Gerar nova URL"}
          </button>
        </div>
        {settings.data.account_webhooks.length > 0 && (
          <details className="rounded-xl border border-line-soft bg-surface-inset p-4">
            <summary className="cursor-pointer text-sm font-medium text-[#dfe4ff]">
              Atribuir as vendas de um bot a uma conta do Instagram
            </summary>
            <p className="mt-2 text-xs leading-5 text-[#94a3b8]">
              O Sharkbot não envia qual conta do Instagram originou o lead. Se um bot atende a uma
              única conta, cadastre nele a URL dessa conta: as vendas desse bot passam a aparecer
              nas métricas da conta. Sem isso, as vendas contam só no total do workspace.
            </p>
            <ul className="mt-3 max-h-72 space-y-2 overflow-y-auto pr-1">
              {settings.data.account_webhooks.map((item) => (
                <li className="flex items-center gap-2" key={item.account_id}>
                  <span className="w-32 shrink-0 truncate text-xs text-[#cbd5e1]">@{item.username}</span>
                  <input
                    aria-label={`URL do webhook para @${item.username}`}
                    className="min-h-9 min-w-0 flex-1 rounded-lg border border-line bg-surface px-2 font-mono text-[11px] text-[#94a3b8]"
                    readOnly
                    value={item.webhook_url}
                  />
                  <button
                    aria-label={`Copiar URL de @${item.username}`}
                    className="btn-ghost !min-h-9 !px-2"
                    onClick={() => {
                      void navigator.clipboard
                        .writeText(item.webhook_url)
                        .then(() => setCopyFeedback(`URL de @${item.username} copiada.`))
                        .catch(() => setCopyFeedback("Não foi possível copiar automaticamente."));
                    }}
                    type="button"
                  >
                    <Copy size={14} />
                  </button>
                </li>
              ))}
            </ul>
          </details>
        )}
      </section>
      <SharkAccountsPanel />
    </div>
  );
}
