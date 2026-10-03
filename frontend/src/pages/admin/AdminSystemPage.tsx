import { useQuery } from "@tanstack/react-query";
import { Settings2 } from "lucide-react";

import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { apiRequest } from "@/services/api";

type SystemSetting = {
  key: string;
  value: unknown;
  is_public: boolean;
  updated_at: string;
};

export function AdminSystemPage() {
  const settings = useQuery({
    queryKey: ["admin", "system-settings"],
    queryFn: () => apiRequest<SystemSetting[]>("/api/admin/system/settings"),
  });

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs font-medium uppercase tracking-[0.16em] text-[#7186ff]">
          Administração
        </p>
        <h2 className="mt-2 text-2xl font-semibold tracking-[-0.045em] text-[#f5f7fb] sm:text-3xl">
          Sistema
        </h2>
        <p className="mt-2 text-sm text-[#94a3b8]">
          Configurações operacionais não sensíveis da plataforma.
        </p>
      </div>

      {settings.isLoading ? (
        <LoadingState label="Carregando configurações" />
      ) : settings.error ? (
        <ErrorState message="Não foi possível carregar as configurações do sistema." />
      ) : settings.data?.length ? (
        <section className="space-y-3">
          {settings.data.map((setting) => (
            <article
              key={setting.key}
              className="flex flex-col gap-3 rounded-xl border border-[#202838] bg-[#0d1015] p-4 sm:flex-row sm:items-center sm:justify-between"
            >
              <div>
                <p className="text-sm font-medium text-[#e6eaf2]">{setting.key}</p>
                <p className="mt-1 text-xs text-[#64748b]">
                  {setting.is_public ? "Pública" : "Operacional"} · Atualizada{" "}
                  {new Date(setting.updated_at).toLocaleString("pt-BR", {
                    timeZone: "America/Sao_Paulo",
                  })}
                </p>
              </div>
              <code className="max-w-full overflow-auto rounded-lg border border-[#202838] bg-[#090b0e] px-3 py-2 text-xs text-[#aeb9ce]">
                {JSON.stringify(setting.value)}
              </code>
            </article>
          ))}
        </section>
      ) : (
        <div className="space-y-4">
          <EmptyState message="Ainda não há configurações operacionais cadastradas." />
          <p className="flex items-center gap-2 text-xs text-[#64748b]">
            <Settings2 size={14} />
            Credenciais e chaves permanecem exclusivamente nas variáveis seguras do Render.
          </p>
        </div>
      )}
    </div>
  );
}
