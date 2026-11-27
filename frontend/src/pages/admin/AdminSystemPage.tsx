import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Gauge, Settings2 } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { apiRequest } from "@/services/api";

type SystemSetting = {
  key: string;
  value: unknown;
  is_public: boolean;
  updated_at: string;
};

type SendRate = { rate: number; default: number };

function BotSendRateCard() {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ["admin", "bot-send-rate"],
    queryFn: () => apiRequest<SendRate>("/api/bots/send-rate"),
  });
  const [value, setValue] = useState<string>("");
  useEffect(() => {
    if (query.data) setValue(String(query.data.rate));
  }, [query.data]);

  const save = useMutation({
    mutationFn: (rate: number) => apiRequest<{ rate: number }>("/api/bots/send-rate", { method: "PUT", body: { rate } }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["admin", "bot-send-rate"] }),
  });

  const rate = Number(value);
  const valid = Number.isFinite(rate) && rate >= 0 && rate <= 30;
  const dirty = query.data ? rate !== query.data.rate : false;

  return (
    <section className="rounded-xl border border-line-soft bg-surface p-4">
      <div className="flex items-center gap-2">
        <Gauge size={18} className="text-accent" />
        <h3 className="text-sm font-semibold text-fg">Fila de envio dos bots (rate limit)</h3>
      </div>
      <p className="mt-1 text-xs text-muted">
        Limite de mensagens por segundo, por bot, para o Telegram. As mensagens entram numa fila automática e saem nesse
        ritmo, evitando banimento por envio em massa (downsells, follow-ups e remarketing em lote). <strong>0 = sem limite</strong>.
        Teto do Telegram ≈ 30/s. Aplicado por container — com vários containers o total é multiplicado, então deixe uma margem.
      </p>
      {query.isLoading ? (
        <LoadingState label="Carregando" />
      ) : query.error ? (
        <ErrorState message="Não foi possível carregar o rate limit." />
      ) : (
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <label className="text-xs text-muted">
            Mensagens por segundo (por bot)
            <input
              className="field mt-1 !w-40"
              type="number"
              min={0}
              max={30}
              step={0.5}
              value={value}
              onChange={(event) => setValue(event.target.value)}
            />
          </label>
          <Button disabled={!valid || !dirty || save.isPending} onClick={() => valid && save.mutate(rate)}>
            {save.isPending ? "Salvando…" : "Salvar"}
          </Button>
          {query.data && (
            <span className="text-xs text-muted">Padrão: {query.data.default}/s</span>
          )}
          {!valid && <span className="text-xs text-warning">Use um valor entre 0 e 30.</span>}
          {save.isSuccess && !dirty && <span className="text-xs text-success">Salvo e aplicado.</span>}
        </div>
      )}
    </section>
  );
}

export function AdminSystemPage() {
  const settings = useQuery({
    queryKey: ["admin", "system-settings"],
    queryFn: () => apiRequest<SystemSetting[]>("/api/admin/system/settings"),
  });

  return (
    <div className="space-y-4">
      <div>
        <h2 className="mt-2 text-2xl font-semibold tracking-[-0.045em] text-fg sm:text-3xl">
          Sistema
        </h2>
      </div>

      <BotSendRateCard />

      {settings.isLoading ? (
        <LoadingState label="Carregando configurações" />
      ) : settings.error ? (
        <ErrorState message="Não foi possível carregar as configurações do sistema." />
      ) : settings.data?.length ? (
        <section className="space-y-3">
          {settings.data.map((setting) => (
            <article
              key={setting.key}
              className="flex flex-col gap-3 rounded-xl border border-line-soft bg-surface p-4 sm:flex-row sm:items-center sm:justify-between"
            >
              <div>
                <p className="text-sm font-medium text-fg">{setting.key}</p>
                <p className="mt-1 text-xs text-muted">
                  {setting.is_public ? "Pública" : "Operacional"} · Atualizada{" "}
                  {new Date(setting.updated_at).toLocaleString("pt-BR", {
                    timeZone: "America/Sao_Paulo",
                  })}
                </p>
              </div>
              <code className="max-w-full overflow-auto rounded-lg border border-line-soft bg-surface-inset px-3 py-2 text-xs text-fg-2">
                {JSON.stringify(setting.value)}
              </code>
            </article>
          ))}
        </section>
      ) : (
        <div className="space-y-4">
          <EmptyState message="Ainda não há configurações operacionais cadastradas." />
          <p className="flex items-center gap-2 text-xs text-muted">
            <Settings2 size={14} />
            Credenciais e chaves permanecem exclusivamente nas variáveis seguras do Render.
          </p>
        </div>
      )}
    </div>
  );
}
