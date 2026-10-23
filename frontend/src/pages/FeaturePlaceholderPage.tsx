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
    <section className="mx-auto max-w-3xl rounded-xl border border-line-soft bg-surface p-4 sm:p-6">
      <h2 className="mt-2 text-2xl font-semibold tracking-[-0.045em] text-fg">
        {title}
      </h2>
      <p className="mt-3 text-sm leading-6 text-muted">
        Em desenvolvimento. Este espaço será conectado quando o módulo for
        implementado, sem exibir dados de demonstração.
      </p>
    </section>
  );
}
