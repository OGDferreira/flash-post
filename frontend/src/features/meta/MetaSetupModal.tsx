import { ExternalLink } from "lucide-react";

import { Modal } from "@/components/ui/Modal";

const steps: { title: string; body: string }[] = [
  {
    title: "Crie o app na Meta",
    body: "Em developers.facebook.com, abra Meus apps → Criar app e escolha o tipo Business. A conta precisa ter o 2FA ativo.",
  },
  {
    title: "Adicione o produto Instagram",
    body: "No painel do app, adicione Instagram → API setup with Instagram login (login com Instagram).",
  },
  {
    title: "Cadastre a URL de callback",
    body: "Em Business login settings → OAuth redirect URIs, cole exatamente a URL de callback mostrada no FlashPost e salve. Ela precisa ser idêntica, inclusive o https. Confira se o painel não acrescentou uma barra no final.",
  },
  {
    title: "Copie o App ID e o App Secret do Instagram",
    body: "Na mesma tela (Business login settings) use o Instagram App ID e o Instagram App Secret. Não use os de Configurações básicas do app.",
  },
  {
    title: "Adicione a conta como testadora do app",
    body: "Em Funções do app, adicione o perfil do Instagram como Instagram Tester e aceite o convite no Instagram (Configurações → Apps e sites → Convites de testador). Em modo de desenvolvimento só contas com função no app conseguem conectar.",
  },
  {
    title: "Use uma conta profissional",
    body: "O perfil do Instagram precisa ser Profissional (Empresa ou Criador). Perfil pessoal não é aceito pela API.",
  },
  {
    title: "Cole os dados no FlashPost e conecte",
    body: "Salve o aplicativo aqui, volte em Contas e clique em Conectar conta. Autorize todas as permissões pedidas.",
  },
];

const permissions: [string, string][] = [
  ["instagram_business_basic", "Ler perfil e dados básicos da conta; renova o token."],
  ["instagram_business_content_publish", "Publicar Reels e fotos pelo FlashPost."],
  ["instagram_business_manage_insights", "Ler métricas (visualizações, alcance, interações)."],
];

export function MetaSetupModal({ open, onClose, callbackUrl }: { open: boolean; onClose: () => void; callbackUrl?: string }) {
  return (
    <Modal
      description="Passo a passo curto para conectar contas do Instagram ao FlashPost."
      footer={
        <button className="btn-primary" onClick={onClose} type="button">
          Entendi
        </button>
      }
      onClose={onClose}
      open={open}
      title="Como configurar o app da Meta"
    >
      <ol className="space-y-3">
        {steps.map((step, index) => (
          <li className="flex gap-3" key={step.title}>
            <span className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-full bg-[#536dfe]/25 text-xs font-semibold text-[#dfe4ff]">
              {index + 1}
            </span>
            <div className="min-w-0">
              <p className="text-sm font-medium text-[#f5f7fb]">{step.title}</p>
              <p className="mt-0.5 text-xs leading-5 text-[#94a3b8]">{step.body}</p>
              {index === 2 && callbackUrl && (
                <code className="mt-1.5 block break-all rounded-lg border border-line-soft bg-surface-inset px-2 py-1.5 text-[11px] text-[#cbd5e1]">
                  {callbackUrl}
                </code>
              )}
            </div>
          </li>
        ))}
      </ol>
      <div className="mt-4 rounded-xl border border-line-soft bg-surface-inset p-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-[#8295ff]">Permissões pedidas na autorização</p>
        <ul className="mt-2 space-y-1.5">
          {permissions.map(([name, why]) => (
            <li className="text-xs leading-5 text-[#94a3b8]" key={name}>
              <code className="text-[#dfe4ff]">{name}</code> — {why}
            </li>
          ))}
        </ul>
        <p className="mt-2 text-[11px] leading-5 text-[#64748b]">
          Com acesso Padrão, o app atende contas que você possui ou administra e adicionou ao app. Para contas de terceiros é
          preciso Acesso Avançado (App Review da Meta).
        </p>
      </div>
      <a
        className="mt-3 inline-flex items-center gap-1.5 text-xs text-[#aab7ff] hover:text-white"
        href="https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/business-login"
        rel="noreferrer"
        target="_blank"
      >
        Documentação oficial da Meta <ExternalLink size={12} />
      </a>
    </Modal>
  );
}
