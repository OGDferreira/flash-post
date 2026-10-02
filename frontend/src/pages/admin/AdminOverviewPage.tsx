import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  Blocks,
  ShieldCheck,
  UserCheck,
  Users,
} from "lucide-react";

import { ErrorState, LoadingState } from "@/components/PageState";
import { apiRequest, type AdminSummary } from "@/services/api";

export function AdminOverviewPage() {
  const summary = useQuery({
    queryKey: ["admin", "summary"],
    queryFn: () => apiRequest<AdminSummary>("/api/admin/summary"),
  });

  if (summary.isLoading) return <LoadingState label="Carregando indicadores" />;
  if (summary.error || !summary.data) {
    return <ErrorState message="Não foi possível carregar os dados administrativos." />;
  }

  const cards = [
    { label: "Usuários totais", value: summary.data.users_total, icon: Users },
    { label: "Workspaces", value: summary.data.workspaces_total, icon: Blocks },
    { label: "Owners", value: summary.data.owners, icon: ShieldCheck },
    { label: "Collaborators", value: summary.data.collaborators, icon: UserCheck },
    { label: "Usuários ativos", value: summary.data.active_users, icon: Activity },
  ];

  return (
    <div className="space-y-8">
      <div>
        <p className="text-xs font-medium uppercase tracking-[0.16em] text-[#7186ff]">
          Plataforma
        </p>
        <h2 className="mt-2 text-2xl font-semibold tracking-[-0.045em] text-[#f5f7fb] sm:text-3xl">
          Visão geral
        </h2>
        <p className="mt-2 text-sm text-[#94a3b8]">
          Indicadores reais de usuários e workspaces cadastrados.
        </p>
      </div>

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {cards.map(({ label, value, icon: Icon }) => (
          <article
            key={label}
            className="rounded-xl border border-[#202838] bg-[#0d1015] p-5"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium uppercase tracking-[0.12em] text-[#64748b]">
                {label}
              </span>
              <Icon size={17} className="text-[#7186ff]" strokeWidth={1.8} />
            </div>
            <p className="mt-5 text-3xl font-semibold tracking-[-0.05em] text-[#f5f7fb]">
              {value}
            </p>
          </article>
        ))}
      </section>
    </div>
  );
}
