import { useQuery } from "@tanstack/react-query";
import { motion, useReducedMotion } from "framer-motion";
import { Activity, Building2, ShieldCheck, UserRound } from "lucide-react";

import { useAuth } from "@/features/auth/AuthProvider";
import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { apiRequest, type Workspace } from "@/services/api";

export function DashboardPage() {
  const { user } = useAuth();
  const reduceMotion = useReducedMotion();
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
    <div className="dashboard-ambient mx-auto w-full max-w-[1240px] space-y-8">
      <section className="grid min-h-[min(680px,calc(100svh-150px))] items-center gap-8 py-5 md:gap-10 lg:grid-cols-[1.12fr_0.88fr] lg:gap-14 xl:gap-[68px]">
        <motion.div
          initial={reduceMotion ? false : { opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55, ease: "easeOut" }}
          className="max-w-[610px] text-center lg:text-left"
        >
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-[#7186ff]">
            Seu espaço
          </p>
          <h2 className="mt-3 text-3xl font-semibold tracking-[-0.055em] text-[#f5f7fb] sm:text-4xl lg:text-[46px] lg:leading-[1.12]">
            Olá, {user?.nickname ?? "bem-vindo"}
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-sm leading-7 text-[#94a3b8] sm:text-base lg:mx-0">
            A base da sua operação está pronta. As métricas aparecerão aqui quando
            os módulos correspondentes forem implementados.
          </p>
        </motion.div>

        <motion.section
          initial={reduceMotion ? false : { opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.65, delay: 0.1, ease: "easeOut" }}
          whileHover={reduceMotion ? undefined : { y: -3 }}
          className="rounded-2xl border border-[#202838] bg-[#0d1015]/95 p-6 transition-[border-color,box-shadow] duration-300 hover:border-[#536dfe]/50 hover:shadow-[0_18px_54px_rgba(7,8,9,0.35)] sm:p-8"
        >
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.14em] text-[#7186ff]">
              Próximos módulos
            </p>
            <h3 className="mt-3 text-lg font-semibold tracking-[-0.025em] text-[#f5f7fb] sm:text-xl">
              Uma fundação segura para crescer
            </h3>
          </div>
          <div className="mt-5">
            <EmptyState message="Contas, publicações, analytics e integrações serão adicionados nas próximas fases." />
          </div>
        </motion.section>
      </section>

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map(({ label, value, detail, icon: Icon }) => (
          <article
            key={label}
            className="min-w-0 rounded-xl border border-[#202838] bg-[#0d1015] p-5 transition-[border-color,transform] duration-200 hover:-translate-y-0.5 hover:border-[#536dfe]/35"
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
    </div>
  );
}
