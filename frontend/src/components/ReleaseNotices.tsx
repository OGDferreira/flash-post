import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { Modal } from "@/components/ui/Modal";
import { useAuth } from "@/features/auth/AuthProvider";
import { canChooseHome } from "@/features/auth/homePanel";
import { apiRequest, type User } from "@/services/api";

type Audience = "owner" | "collaborator" | "admin";
type Item = { text: string; to?: Audience[] };

/** What changed in this release, by who sees it (owner = an operation's owner or sócio). */
const NEWS: Item[] = [
  { text: "📊 Análises completas no Flash Bot: filtros por bot, fluxo e plano, o que vende e o que não vende, horários e clientes.", to: ["owner", "admin"] },
  { text: "▶️ Testar funil: prévia ao vivo no editor e simulação de pagamento, entrega, upsell e downsell, sem cobrar nada.", to: ["owner", "admin"] },
  { text: "✅ Mensagem de pagamento aprovado opcional, antes da entrega.", to: ["owner", "admin"] },
  { text: "🛒 Order bump pode usar a entrega padrão do funil.", to: ["owner", "admin"] },
  { text: "📁 Métricas por pasta de contas e ranking de stories por interação.", to: ["owner", "admin"] },
  { text: "📂 Cards das pastas com contas, views de hoje e de 7 dias e a melhor conta.", to: ["owner", "admin"] },
  { text: "⭐ Marcação de destaques em cada conta, com filtro “Sem destaques”." },
  { text: "💳 Chaves Pix favoritas na carteira e “Sacar tudo” da SnakePay corrigido.", to: ["owner", "admin"] },
  { text: "📱 Widget novo: total do dia, vendas Flash e Shark separadas, views, 7 temas trocados com um toque e botão “Atualizar widget”.", to: ["owner", "admin"] },
  { text: "🎨 Ícone escuro para o app e as notificações (Configurações)." },
  { text: "👥 Mudar o tipo de conta dos usuários e liberar loops, fluxos e bots para os sócios.", to: ["admin"] },
];

const NOTICES = ["novidades-2026-11", "reinstalar-2026-11"] as const;

function audienceOf(user: User): Audience {
  if (user.role === "SUPER_ADMIN") return "admin";
  return user.workspace_role === "COLLABORATOR" ? "collaborator" : "owner";
}

/** One-time pop-ups after an update: the release notes, then "reinstall the app and widget".
 *  Saved on the account, so another device or a reinstall never shows them again. */
export function ReleaseNotices() {
  const { user } = useAuth();
  const cache = useQueryClient();
  const navigate = useNavigate();
  const [closed, setClosed] = useState<string[]>([]);
  const seen = useMutation({
    mutationFn: (id: string) => apiRequest<User>("/api/profile/preferences", { method: "PATCH", body: { seen_notice: id } }),
    onSuccess: (updated) => {
      cache.setQueryData(["auth", "me"], updated);
      cache.setQueryData(["profile"], updated);
    },
  });
  if (!user || user.impersonator_name) return null;
  // the "where do you want to start?" question comes first
  if (canChooseHome(user) && !user.home_panel) return null;
  const already = new Set([...(user.seen_notices ?? []), ...closed]);
  const current = NOTICES.find((id) => !already.has(id));
  if (!current) return null;
  const audience = audienceOf(user);
  const close = () => {
    setClosed((list) => [...list, current]);
    seen.mutate(current);
  };

  if (current === "novidades-2026-11") {
    const items = NEWS.filter((item) => !item.to || item.to.includes(audience));
    return (
      <Modal
        description="As últimas atualizações do Flash."
        footer={<button className="btn-primary w-full sm:w-auto" onClick={close} type="button">Entendi</button>}
        onClose={close}
        open
        title="🚀 Novidades no Flash"
      >
        <ul className="space-y-2 text-sm leading-6 text-fg-2">
          {items.map((item) => (
            <li className="rounded-xl border border-line-soft bg-surface-inset px-3 py-2" key={item.text}>{item.text}</li>
          ))}
        </ul>
      </Modal>
    );
  }

  const widget = audience !== "collaborator";
  return (
    <Modal
      description={widget ? "Para receber as novas funções no iPhone, reinstale o app e atualize o widget." : "Para receber as novas funções no iPhone, reinstale o app."}
      footer={
        <div className="flex w-full flex-wrap justify-end gap-2">
          <button className="btn-ghost" onClick={close} type="button">Depois</button>
          <button
            className="btn-primary"
            onClick={() => {
              close();
              navigate("/configuracoes");
            }}
            type="button"
          >
            Abrir Configurações
          </button>
        </div>
      }
      onClose={close}
      open
      title="📲 Reinstale o app"
    >
      <div className="space-y-3 text-sm leading-6 text-fg-2">
        <div className="rounded-xl border border-line-soft bg-surface-inset p-3">
          <p className="font-semibold text-fg">App</p>
          <ol className="mt-1 list-decimal space-y-0.5 pl-5 text-xs">
            <li>Em Configurações, escolha o ícone do app e toque em <b>Copiar link de instalação</b>.</li>
            <li>Segure o ícone do Flash na tela de início → <b>Remover app</b>.</li>
            <li>Cole o link no Safari → <b>Compartilhar</b> → <b>Adicionar à Tela de Início</b>.</li>
            <li>Abra o Flash, entre na conta e ative as notificações de novo.</li>
          </ol>
        </div>
        {widget && (
          <div className="rounded-xl border border-line-soft bg-surface-inset p-3">
            <p className="font-semibold text-fg">Widget</p>
            <ol className="mt-1 list-decimal space-y-0.5 pl-5 text-xs">
              <li>Em Configurações → <b>Widget de vendas no iPhone</b>, toque em <b>Copiar script</b> e cole por cima no Scriptable (só desta vez).</li>
              <li>Depois disso, as próximas versões chegam pelo botão <b>Atualizar widget</b>.</li>
            </ol>
          </div>
        )}
      </div>
    </Modal>
  );
}
