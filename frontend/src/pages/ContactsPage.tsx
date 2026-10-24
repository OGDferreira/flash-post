import { ArrowUpRight, Instagram, LifeBuoy, MessageCircle, Send, Users } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { SUPPORT_WHATSAPP_LABEL, contactChannels, whatsappLink } from "@/lib/contacts";

type ChannelProps = {
  icon: LucideIcon;
  title: string;
  description: string;
  action: string;
  href: string | null;
  to?: string;
  detail?: string;
};

function Channel({ icon: Icon, title, description, action, href, to, detail }: ChannelProps) {
  const live = Boolean(href || to);
  const body = (
    <>
      <div className="flex items-start gap-3">
        <span className="grid size-11 shrink-0 place-items-center rounded-2xl border border-line bg-brand-soft text-accent">
          <Icon size={20} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-base font-semibold text-fg">{title}</h2>
            {!live && <Badge tone="warning">Em breve</Badge>}
          </div>
          <p className="mt-1 text-sm leading-6 text-muted">{description}</p>
          {detail && <p className="mt-1 text-xs text-fg-2">{detail}</p>}
        </div>
      </div>
      <span className={`mt-4 inline-flex items-center gap-1.5 text-sm font-medium ${live ? "text-accent" : "text-muted"}`}>
        {live ? action : "Disponível em breve"}
        {live && <ArrowUpRight size={15} />}
      </span>
    </>
  );
  const cls = "dashboard-card block rounded-2xl p-5";
  if (to) return <Link className={cls} to={to}>{body}</Link>;
  if (href) return <a className={cls} href={href} rel="noopener noreferrer" target="_blank">{body}</a>;
  return <div aria-disabled="true" className={`${cls} opacity-80`}>{body}</div>;
}

export function ContactsPage() {
  const { instagram, community, telegram } = contactChannels;
  return (
    <div className="mx-auto max-w-[1100px] space-y-5">
      <header>
        <h1 className="text-2xl font-semibold text-fg sm:text-3xl">Contatos</h1>
      </header>

      <section className="grid gap-4 sm:grid-cols-2" aria-label="Canais oficiais">
        <Channel
          action="Chamar no WhatsApp"
          description="Atendimento direto com a equipe para dúvidas, problemas e sugestões."
          detail={SUPPORT_WHATSAPP_LABEL}
          href={whatsappLink("Olá! Preciso de ajuda com o Flash.")}
          icon={MessageCircle}
          title="WhatsApp"
        />
        <Channel
          action="Abrir suporte"
          description="Abra um chamado com o passo a passo do problema e acompanhe a resposta."
          href={null}
          icon={LifeBuoy}
          title="Suporte"
          to="/feature/support"
        />
        <Channel
          action="Entrar na comunidade"
          description="Grupo no WhatsApp para trocar experiências, tirar dúvidas e receber novidades."
          href={community.url}
          icon={Users}
          title="Comunidade"
        />
        <Channel
          action="Ver no Instagram"
          description="Perfil oficial do Flash, com conteúdos criados e publicados automaticamente pela própria plataforma."
          detail={instagram.handle ?? undefined}
          href={instagram.url}
          icon={Instagram}
          title="Instagram do Flash"
        />
        <Channel
          action="Abrir no Telegram"
          description="Bot do Flash no Telegram: tudo em um só lugar, direto no seu chat."
          href={telegram.url}
          icon={Send}
          title="Bot do Telegram"
        />
      </section>
    </div>
  );
}
