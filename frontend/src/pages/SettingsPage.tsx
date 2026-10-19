import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  Bell,
  Blocks,
  ChevronRight,
  CircleDollarSign,
  KeyRound,
  Moon,
  Palette,
  PlugZap,
  Puzzle,
  Settings,
  Settings2,
  Sun,
  UserRound,
} from "lucide-react";

import { AppearanceCard } from "@/components/AppearanceCard";
import { useAuth } from "@/features/auth/AuthProvider";
import { applyTheme, getTheme, type Theme } from "@/lib/theme";

type Item = { to: string; title: string; text: string; icon: ReactNode; owner?: boolean };

const sections: { id: string; title: string; icon: ReactNode; items: Item[] }[] = [
  {
    id: "integracoes",
    title: "Integrações",
    icon: <PlugZap size={18} />,
    items: [
      {
        to: "/feature/integrations",
        title: "Webhooks e API",
        text: "Endpoints da SmokePay e da SharkBot: URL, segredo e parte da venda que conta como faturamento.",
        icon: <KeyRound size={18} />,
        owner: true,
      },
      {
        to: "/feature/bots?tab=gateways",
        title: "Gateways de pagamento",
        text: "SmokePay ou SnakePay para gerar os Pix dos robôs, por fluxo ou para todos.",
        icon: <CircleDollarSign size={18} />,
        owner: true,
      },
      {
        to: "/feature/meta-apps",
        title: "Apps Meta (Instagram)",
        text: "Aplicativos da Meta usados para conectar as contas do Instagram.",
        icon: <Settings2 size={18} />,
        owner: true,
      },
      {
        to: "/feature/extensions",
        title: "Extensões",
        text: "Extensão do navegador e ferramentas que conversam com o FlashPost.",
        icon: <Puzzle size={18} />,
      },
    ],
  },
  {
    id: "conta",
    title: "Conta e avisos",
    icon: <UserRound size={18} />,
    items: [
      { to: "/profile", title: "Perfil", text: "Nome, apelido, foto e senha.", icon: <UserRound size={18} /> },
      {
        to: "/feature/notifications",
        title: "Notificações",
        text: "Avisos no celular de vendas, comissões, metas e contas desconectadas.",
        icon: <Bell size={18} />,
        owner: true,
      },
    ],
  },
];

function ThemeSwitch() {
  const [theme, setTheme] = useState<Theme>(getTheme);
  useEffect(() => {
    const follow = () => setTheme(getTheme());
    window.addEventListener("flashpost:theme", follow);
    return () => window.removeEventListener("flashpost:theme", follow);
  }, []);
  return (
    <section className="rounded-xl border border-line-soft bg-surface p-4 sm:p-5">
      <div className="flex items-center gap-2">
        <Palette className="text-accent" size={18} />
        <h2 className="text-base font-semibold text-fg">Modo da tela</h2>
      </div>
      <div className="mt-3 inline-flex rounded-full border border-line-soft p-1" role="radiogroup">
        {([["dark", "Escuro", Moon], ["light", "Claro", Sun]] as const).map(([value, label, Icon]) => (
          <button
            aria-checked={theme === value}
            className={`flex min-h-10 items-center gap-2 rounded-full px-5 text-sm font-medium transition ${theme === value ? "bg-brand text-white" : "text-muted hover:text-fg"}`}
            key={value}
            onClick={() => applyTheme(value, true)}
            role="radio"
            type="button"
          >
            <Icon size={15} /> {label}
          </button>
        ))}
      </div>
      <p className="mt-2 text-xs text-muted">Também dá para trocar pelo botão de sol/lua no topo da tela.</p>
    </section>
  );
}

/** One place for everything about how the site works for you: look, account, integrations. */
export function SettingsPage() {
  const { user } = useAuth();
  const owner = user?.workspace_role === "OWNER" || user?.role === "SUPER_ADMIN";
  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <header>
        <p className="text-xs font-medium uppercase tracking-[0.16em] text-accent">Ajustes</p>
        <h1 className="mt-2 flex items-center gap-2 text-2xl font-semibold text-fg sm:text-3xl">
          <Settings className="text-accent" size={26} /> Configurações
        </h1>
        <p className="mt-2 text-sm text-muted">Tema e aparência, conta, avisos e as integrações com API, webhooks e gateways.</p>
      </header>

      <div className="space-y-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.12em] text-muted">
          <Palette size={16} /> Aparência
        </h2>
        <ThemeSwitch />
        <AppearanceCard />
      </div>

      {sections.map((section) => {
        const items = section.items.filter((item) => owner || !item.owner);
        if (items.length === 0) return null;
        return (
          <div className="space-y-3" id={section.id} key={section.id}>
            <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.12em] text-muted">
              {section.icon} {section.title}
            </h2>
            <div className="grid gap-2 sm:grid-cols-2">
              {items.map((item) => (
                <Link
                  className="group flex items-center gap-3 rounded-xl border border-line-soft bg-surface p-4 transition hover:border-accent/60"
                  key={item.to}
                  to={item.to}
                >
                  <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-brand-soft text-accent">{item.icon}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-semibold text-fg">{item.title}</span>
                    <span className="block text-xs leading-5 text-muted">{item.text}</span>
                  </span>
                  <ChevronRight className="shrink-0 text-muted transition group-hover:translate-x-0.5 group-hover:text-accent" size={18} />
                </Link>
              ))}
            </div>
          </div>
        );
      })}
      {!owner && (
        <p className="flex items-center gap-2 text-xs text-muted">
          <Blocks size={14} /> Integrações e gateways ficam com o dono da operação.
        </p>
      )}
    </div>
  );
}
