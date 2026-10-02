import { useParams } from "react-router-dom";

const labels: Record<string, string> = {
  accounts: "Contas",
  loops: "Loops",
  analytics: "Analytics",
  finance: "Financeiro",
  ranking: "Ranking",
  feed: "Feed",
  automations: "Automações",
  integrations: "Integrações",
  collaborators: "Colaboradores",
  notifications: "Notificações",
  settings: "Configurações",
};

export function FeaturePlaceholderPage() {
  const { slug = "" } = useParams();
  const title = labels[slug] ?? "Módulo";

  return (
    <section className="mx-auto max-w-3xl rounded-xl border border-[#202838] bg-[#0d1015] p-6 sm:p-8">
      <p className="text-xs font-medium uppercase tracking-[0.16em] text-[#7186ff]">
        Próxima fase
      </p>
      <h2 className="mt-2 text-2xl font-semibold tracking-[-0.045em] text-[#f5f7fb]">
        {title}
      </h2>
      <p className="mt-3 text-sm leading-6 text-[#94a3b8]">
        Em desenvolvimento. Este espaço será conectado quando o módulo for
        implementado, sem exibir dados de demonstração.
      </p>
    </section>
  );
}
