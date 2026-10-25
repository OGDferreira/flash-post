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

import { HomePanelPreference } from "@/components/HomePanelPreference";
import { AppearanceCard } from "@/components/AppearanceCard";
import { PushSwitch } from "@/components/PushSwitch";
import { useAuth } from "@/features/auth/AuthProvider";
import { copyGeneratedText, copyText } from "@/lib/clipboard";
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
        to: "/bot/gateways",
        title: "Gateways de pagamento",
        text: "SmokePay ou SnakePay para gerar os Pix dos bots, por fluxo ou para todos.",
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
        text: "Extensão do navegador e ferramentas que conversam com o Flash.",
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
    </section>
  );
}

/** The Flash sales widget for the iPhone home screen, through the free Scriptable app. */
const WIDGET_THEMES: { id: WidgetTheme; label: string; swatch: string; text: string }[] = [
  { id: "azul", label: "Roxo", swatch: "linear-gradient(135deg,#8f1dff,#7a00ff 55%,#5b00c4)", text: "#fff" },
  { id: "dark", label: "Escuro", swatch: "linear-gradient(135deg,#12141c,#20264a)", text: "#fff" },
  { id: "white", label: "Branco", swatch: "linear-gradient(135deg,#ffffff,#e7edff)", text: "#0b1530" },
];

function IphoneWidgetCard() {
  const [copied, setCopied] = useState(false);
  const [theme, setTheme] = useState<WidgetTheme>("azul");
  const [token, setToken] = useState<string | null>(null);
  const [copying, setCopying] = useState(false);
  const [copyError, setCopyError] = useState("");
  const script = token ? scriptableWidgetScript(window.location.origin, token, theme) : "";
  // Keep a successfully generated token in memory, even if clipboard permission is denied.
  // A retry or theme change must not invalidate a script already installed on the phone.
  const generate = useMutation({
    mutationFn: () => apiRequest<{ token: string }>("/api/widget/token", { method: "POST" }),
    onSuccess: (result) => setToken(result.token),
  });
  const copy = async () => {
    setCopying(true);
    setCopied(false);
    setCopyError("");
    try {
      if (script) await copyText(script);
      else {
        const ready = generate.mutateAsync().then(({ token: fresh }) => scriptableWidgetScript(window.location.origin, fresh, theme));
        // Attach rejection handlers immediately to both promises, even when permission is denied first.
        const results = await Promise.allSettled([ready, copyGeneratedText(ready)]);
        for (const result of results) if (result.status === "rejected") throw result.reason;
      }
      setCopied(true);
      window.setTimeout(() => setCopied(false), 4000);
    } catch (error) {
      setCopyError(error instanceof ApiError ? error.message : "Toque novamente em Copiar script ou selecione o código abaixo para copiar manualmente.");
    } finally { setCopying(false); }
  };
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
        O script tem uma chave só de leitura. Gerar um novo script em outra visita desliga a chave anterior; repetir a cópia aqui mantém a mesma chave.
      </p>
      <div aria-label="Tema do widget" className="mt-3 flex flex-wrap gap-2" role="radiogroup">
        {WIDGET_THEMES.map((item) => (
          <button
            aria-checked={theme === item.id}
            className={`flex h-14 w-24 flex-col justify-end rounded-xl border-2 px-2.5 pb-1.5 text-left text-xs font-semibold transition ${
              theme === item.id ? "border-accent ring-2 ring-accent/40" : "border-line-soft"
            }`}
            key={item.id}
            onClick={() => { setTheme(item.id); setCopied(false); }}
            role="radio"
            style={{ background: item.swatch, color: item.text }}
            type="button"
          >
            {item.label}
          </button>
        ))}
      </div>
      <p className="mt-1.5 text-[11px] text-muted">
        Dá para trocar em cada widget: segure o widget → Editar widget → em <b>Parameter</b> escreva dark, white ou roxo.
      </p>
      <button className="btn-primary mt-3" disabled={copying} onClick={() => void copy()} type="button">
        {copying ? "Preparando…" : copied ? "Script copiado ✓" : "Copiar script"}
      </button>
      <p role="status" className="mt-2 text-xs text-success">{copied ? "Script completo copiado. Cole no Scriptable." : ""}</p>
      {copyError && <p role="alert" className="mt-2 text-xs text-danger">{copyError}</p>}
      {script && <details className="mt-3" open={!!copyError}>
        <summary className="cursor-pointer text-xs text-muted">Ver script completo / copiar manualmente</summary>
        <textarea aria-label="Script completo do widget" className="field mt-2 h-48 w-full font-mono text-xs"
          readOnly value={script} onFocus={(event) => event.target.select()} />
      </details>}
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
        <h1 className="flex items-center gap-2 text-2xl font-semibold text-fg sm:text-3xl">
          <Settings className="text-accent" size={26} /> Configurações
        </h1>
      </header>

      <HomePanelPreference />

      <div className="space-y-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.12em] text-muted">
          <Palette size={16} /> Aparência
        </h2>
        <ThemeSwitch />
        <AppearanceCard />
        <PushSwitch />
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
