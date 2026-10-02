import { useQuery } from "@tanstack/react-query";
import { Activity, Building2, ShieldCheck, UserRound } from "lucide-react";

import { useAuth } from "@/features/auth/AuthProvider";
import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { apiRequest, type Workspace } from "@/services/api";

export function DashboardPage() {
  const { user } = useAuth();
  const workspace = useQuery({
    queryKey: ["workspace"],
    queryFn: () => apiRequest<Workspace>("/api/workspace"),
    enabled: user?.role !== "SUPER_ADMIN",
    retry: false,
  });

  if (user?.role !== "SUPER_ADMIN" && workspace.isLoading) {
    return <LoadingState label="Carregando seu workspace" />;
  }
  if (workspace.error) {
    return (
      <ErrorState message="Não foi possível carregar seu workspace. Atualize a página ou fale com o suporte." />
    );
  }

  const cards = [
    {
      label: "Workspace",
      value: workspace.data?.name ?? "Acesso global",
      detail: workspace.data?.slug ?? "Conta administrativa da plataforma",
      icon: Building2,
    },
    {
      label: "Usuário",
      value: user?.full_name ?? "—",
      detail: user?.email ?? "",
      icon: UserRound,
    },
    {
      label: "Permissão",
      value: user?.role ?? "—",
      detail: workspace.data?.role ?? "FlashPost",
      icon: ShieldCheck,
    },
    {
      label: "Sistema",
      value: "Online",
      detail: "API disponível",
      icon: Activity,
    },
  ];

  return (
    <div className="space-y-8">
      <div>
        <p className="text-xs font-medium uppercase tracking-[0.16em] text-[#7186ff]">
          Seu espaço
        </p>
        <h2 className="mt-2 text-2xl font-semibold tracking-[-0.045em] text-[#f5f7fb] sm:text-3xl">
          Visão geral
        </h2>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-[#94a3b8]">
          A base da sua operação está pronta. As métricas aparecerão aqui quando
          os módulos correspondentes forem implementados.
        </p>
      </div>

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map(({ label, value, detail, icon: Icon }) => (
          <article
            key={label}
            className="min-w-0 rounded-xl border border-[#202838] bg-[#0d1015] p-5"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium uppercase tracking-[0.12em] text-[#64748b]">
                {label}
              </span>
              <Icon size={17} className="text-[#7186ff]" strokeWidth={1.8} />
            </div>
            <p className="mt-5 truncate text-lg font-semibold tracking-[-0.035em] text-[#f5f7fb]">
              {value}
            </p>
            <p className="mt-1 truncate text-xs text-[#64748b]">{detail}</p>
          </article>
        ))}
      </section>

      <section className="rounded-xl border border-[#202838] bg-[#0d1015] p-5 sm:p-6">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.14em] text-[#64748b]">
            Próximos módulos
          </p>
          <h3 className="mt-2 text-base font-semibold text-[#e6eaf2]">
            Uma fundação segura para crescer
          </h3>
        </div>
        <div className="mt-5">
          <EmptyState message="Contas, publicações, analytics e integrações serão adicionados nas próximas fases." />
        </div>
      </section>
    </div>
  );
}
