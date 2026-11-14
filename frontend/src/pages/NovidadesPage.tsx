import { Gauge, MessagesSquare, RefreshCw, ShieldCheck, Sparkles } from "lucide-react";

/** Comunicado da migração de domínio (onrender → flashpost.tech). Alvo do clique na notificação. */
export function NovidadesPage() {
  return (
    <div className="mx-auto max-w-[760px] space-y-5">
      <header className="glass-panel overflow-hidden p-6">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-accent">
          <Sparkles size={14} /> Atualização importante
        </div>
        <h1 className="mt-3 text-2xl font-semibold text-fg sm:text-3xl">
          A FlashPost agora é <span className="text-accent">flashpost.tech</span>
        </h1>
        <p className="mt-2 text-sm leading-6 text-fg-2">
          Trocamos de endereço e migramos a plataforma para uma infraestrutura própria, mais rápida e estável.
          O antigo <span className="font-medium text-muted line-through">flashpost.onrender.com</span> sai de cena —
          o novo lar é <span className="font-medium text-fg">flashpost.tech</span>.
        </p>
      </header>

      <section className="glass-panel flex items-start gap-3 border-l-2 border-l-success p-5">
        <ShieldCheck className="mt-0.5 shrink-0 text-success" size={20} />
        <div>
          <h2 className="text-sm font-semibold text-fg">Suas contas, bots e dados continuam salvos</h2>
          <p className="mt-1 text-sm leading-6 text-fg-2">
            Nada foi perdido na migração. Contas Instagram conectadas, bots do Telegram, fluxos, vendas e
            saldos seguem exatamente como estavam. Todos os processos continuam rodando normalmente.
          </p>
        </div>
      </section>

      <section className="glass-panel p-5">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-fg">
          <RefreshCw size={16} className="text-accent" /> Reinstale o app e o widget no novo domínio
        </h2>
        <p className="mt-1 text-sm leading-6 text-fg-2">
          O app instalado e o widget apontavam para o endereço antigo. Para voltar a receber tudo no novo
          domínio, é só reinstalar:
        </p>
        <ol className="mt-3 space-y-2 text-sm leading-6 text-fg-2">
          <li>
            <span className="font-medium text-fg">1.</span> Abra <span className="font-medium text-fg">flashpost.tech</span> no navegador e
            entre na sua conta.
          </li>
          <li>
            <span className="font-medium text-fg">2.</span> Instale o app novamente pelo botão de instalar do navegador
            (ou "Adicionar à tela inicial" no celular).
          </li>
          <li>
            <span className="font-medium text-fg">3.</span> Ative as notificações de novo para o widget voltar a avisar das vendas.
          </li>
        </ol>
        <p className="mt-3 text-xs leading-5 text-muted">
          Pode remover o atalho antigo do onrender — ele não será mais atualizado.
        </p>
      </section>

      <section className="grid gap-3 sm:grid-cols-2">
        <div className="glass-panel p-5">
          <Gauge className="text-accent" size={20} />
          <h3 className="mt-2 text-sm font-semibold text-fg">Mais desempenho</h3>
          <p className="mt-1 text-sm leading-6 text-fg-2">
            Servidor próprio e dedicado: carregamento mais rápido, conexão mais estável e os bots respondendo
            na hora.
          </p>
        </div>
        <div className="glass-panel p-5">
          <MessagesSquare className="text-accent" size={20} />
          <h3 className="mt-2 text-sm font-semibold text-fg">Chat global</h3>
          <p className="mt-1 text-sm leading-6 text-fg-2">
            Novo espaço pra comunidade trocar ideia dentro da plataforma. Já disponível no menu.
          </p>
        </div>
      </section>

      <p className="pb-2 text-center text-sm text-muted">
        Qualquer dúvida, fale com o suporte. Bom trabalho e boas vendas. ⚡
      </p>
    </div>
  );
}
