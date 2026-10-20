import { useEffect, useState, type ReactNode } from "react";
import { useMutation } from "@tanstack/react-query";
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
  Smartphone,
  Sun,
  UserRound,
} from "lucide-react";

import { AppearanceCard } from "@/components/AppearanceCard";
import { useAuth } from "@/features/auth/AuthProvider";
import { scriptableWidgetScript, type WidgetTheme } from "@/lib/scriptableWidget";
import { applyTheme, getTheme, type Theme } from "@/lib/theme";
import { ApiError, apiRequest } from "@/services/api";

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

/** The FlashBot sales widget for the iPhone home screen, through the free Scriptable app. */
const WIDGET_THEMES: { id: WidgetTheme; label: string; swatch: string; text: string }[] = [
  { id: "azul", label: "Azul", swatch: "linear-gradient(135deg,#3a5ffe,#1e9cfd 55%,#15d6fe)", text: "#fff" },
  { id: "dark", label: "Escuro", swatch: "linear-gradient(135deg,#0b1020,#10204a)", text: "#fff" },
  { id: "white", label: "Branco", swatch: "linear-gradient(135deg,#ffffff,#e8f1ff)", text: "#0b1530" },
];

function IphoneWidgetCard() {
  const [copied, setCopied] = useState(false);
  const [theme, setTheme] = useState<WidgetTheme>("azul");
  const copy = useMutation({
    mutationFn: async () => {
      const { token } = await apiRequest<{ token: string }>("/api/widget/token", { method: "POST" });
      await navigator.clipboard.writeText(scriptableWidgetScript(window.location.origin, token, theme));
    },
    onSuccess: () => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 4000);
    },
  });
  return (
    <section className="rounded-xl border border-line-soft bg-surface p-4 sm:p-5">
      <div className="flex items-center gap-2">
        <Smartphone className="text-accent" size={18} />
        <h2 className="text-base font-semibold text-fg">Widget de vendas no iPhone</h2>
      </div>
      <p className="mt-1 text-sm text-muted">
        Faturamento, lucro, Pix gerados e pagos e o gráfico do dia na tela inicial, pelo app gratuito Scriptable.
      </p>
      <ol className="mt-3 list-decimal space-y-1 pl-5 text-xs leading-5 text-fg-2">
        <li>Instale o <b>Scriptable</b> na App Store.</li>
        <li>Toque em <b>Copiar script</b> aqui, abra o Scriptable, toque em <b>+</b> e cole.</li>
        <li>Na tela inicial, segure um espaço vazio → <b>+</b> → Scriptable → escolha o tamanho → toque no widget e selecione o script.</li>
      </ol>
      <p className="mt-2 text-[11px] leading-5 text-muted">
        Médio e pequeno: faturamento do dia, taxa de conversão, vendas e gráfico. Grande: também lucro e Pix gerados/pagos. Tela de bloqueio: logo,
        valor e número de vendas. Venda nova aparece com um selo verde; tocar no widget abre a versão animada. O iPhone decide quando
        atualizar (pedimos a cada minuto; costuma ser a cada 5 a 15 min). Já instalou antes? Copie de novo e cole por cima no Scriptable.
        O script tem uma chave só de leitura; copiar de novo desliga a anterior.
      </p>
      <div aria-label="Tema do widget" className="mt-3 flex flex-wrap gap-2" role="radiogroup">
        {WIDGET_THEMES.map((item) => (
          <button
            aria-checked={theme === item.id}
            className={`flex h-14 w-24 flex-col justify-end rounded-xl border-2 px-2.5 pb-1.5 text-left text-xs font-semibold transition ${
              theme === item.id ? "border-accent ring-2 ring-accent/40" : "border-line-soft"
            }`}
            key={item.id}
            onClick={() => setTheme(item.id)}
            role="radio"
            style={{ background: item.swatch, color: item.text }}
            type="button"
          >
            {item.label}
          </button>
        ))}
      </div>
      <p className="mt-1.5 text-[11px] text-muted">
        Dá para trocar em cada widget: segure o widget → Editar widget → em <b>Parameter</b> escreva dark, white ou azul.
      </p>
      <button className="btn-primary mt-3" disabled={copy.isPending} onClick={() => copy.mutate()} type="button">
        {copy.isPending ? "Gerando…" : copied ? "Script copiado ✓" : "Copiar script"}
      </button>
      {copy.error && (
        <p className="mt-2 text-xs text-danger">
          {copy.error instanceof ApiError ? copy.error.message : "Não foi possível copiar. Tente de novo."}
        </p>
      )}
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

      {owner && <IphoneWidgetCard />}

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
