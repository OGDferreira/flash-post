import { useEffect, useState, type ReactNode } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
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
import { PeriodFilter, isPeriodReady, periodParams, todayInput, type MetricsPeriod } from "@/features/analytics/period";

type Item = { to: string; title: string; text: string; icon: ReactNode; owner?: boolean; superAdmin?: boolean };

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
        superAdmin: true,
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

/** "Receber notificações de vendas passadas": the sales of a chosen period arrive again as
 *  notifications on the devices with notifications on (oldest first, at most 100). */
function PastSalesCard() {
  const [period, setPeriod] = useState<MetricsPeriod>({ period: "today", start: todayInput(), end: todayInput() });
  const replay = useMutation({
    mutationFn: () =>
      apiRequest<{ count: number; limit: number; period_label: string }>("/api/notifications/past-sales", {
        method: "POST",
        body: periodParams(period),
      }),
  });
  return (
    <section className="rounded-xl border border-line-soft bg-surface p-4 sm:p-5">
      <h3 className="text-base font-semibold text-fg">Receber notificações de vendas passadas</h3>
      <p className="mt-1 text-sm text-muted">
        Escolha o período: as vendas (Flash, Shark e comissões) chegam de novo como notificações, com o horário de cada uma.
      </p>
      <div className="mt-3">
        <PeriodFilter onChange={setPeriod} value={period} />
      </div>
      <button
        className="btn-primary mt-3"
        disabled={replay.isPending || !isPeriodReady(period)}
        onClick={() => replay.mutate()}
        type="button"
      >
        {replay.isPending ? "Preparando…" : "Receber notificações"}
      </button>
      <p className="mt-2 text-xs" role="status">
        {replay.isError ? (
          <span className="text-danger">{replay.error instanceof ApiError ? replay.error.message : "Não foi possível enviar agora."}</span>
        ) : replay.data ? (
          <span className={replay.data.count ? "text-success" : "text-muted"}>
            {replay.data.count
              ? `${replay.data.count} ${replay.data.count === 1 ? "notificação a caminho" : "notificações a caminho"} (${replay.data.period_label}).${replay.data.count >= replay.data.limit ? ` Só as ${replay.data.limit} mais recentes.` : ""}`
              : `Nenhuma venda em ${replay.data.period_label}.`}
          </span>
        ) : (
          <span className="text-muted">Precisa das notificações ativadas neste aparelho.</span>
        )}
      </p>
    </section>
  );
}

type AppIcon = "dark" | "blue" | "purple";
const APP_ICONS: { id: AppIcon; label: string; src: string }[] = [
  { id: "dark", label: "Escuro", src: "/brand/flash-icon-dark-180.png" },
  { id: "blue", label: "Azul", src: "/brand/apple-touch-icon.png" },
  { id: "purple", label: "Roxo", src: "/brand/flash-icon-purple-180.png" },
];

function readAppIcon(): AppIcon | null {
  try {
    const value = localStorage.getItem("flash-app-icon");
    return value === "dark" || value === "blue" || value === "purple" ? value : null;
  } catch {
    return null;
  }
}

/** Saves the choice: this device's install icon (iPhone: also the notifications' icon, taken
 *  when the app is added to the home screen) and the notifications' icon on Android/computers
 *  (read by the service worker from its prefs cache). */
async function applyAppIcon(icon: AppIcon) {
  try {
    localStorage.setItem("flash-app-icon", icon);
  } catch {
    /* private mode: only this visit */
  }
  const apple = document.querySelector<HTMLLinkElement>('link[rel="apple-touch-icon"]');
  if (apple) apple.href = icon === "blue" ? "/brand/apple-touch-icon.png" : `/brand/flash-icon-${icon}-180.png`;
  const manifest = document.querySelector<HTMLLinkElement>('link[rel="manifest"]');
  if (manifest) manifest.href = icon === "blue" ? "/manifest.webmanifest" : `/manifest-${icon}.webmanifest`;
  try {
    const cache = await caches.open("flash-prefs");
    await cache.put("/__prefs/app-icon", new Response(icon, { headers: { "Content-Type": "text/plain" } }));
  } catch {
    /* no Cache API here: the service worker keeps its default */
  }
}

/** "Ícone do app e das notificações": dark, blue or purple. */
function AppIconPicker() {
  const [icon, setIcon] = useState<AppIcon | null>(readAppIcon);
  const [saved, setSaved] = useState(false);
  const [copiedLink, setCopiedLink] = useState(false);
  const isIphone = /iPhone|iPad|iPod/.test(navigator.userAgent);
  return (
    <section className="rounded-xl border border-line-soft bg-surface p-4 sm:p-5">
      <h3 className="text-base font-semibold text-fg">Ícone do app e das notificações</h3>
      <p className="mt-1 text-sm text-muted">Escolha o ícone que aparece na tela de início e nas notificações.</p>
      <div aria-label="Ícone do app" className="mt-3 flex flex-wrap gap-3" role="radiogroup">
        {APP_ICONS.map((item) => (
          <button
            aria-checked={icon === item.id}
            className={`flex w-24 flex-col items-center gap-1.5 rounded-xl border-2 p-2 text-xs font-semibold transition ${
              icon === item.id ? "border-accent bg-brand-soft text-fg" : "border-line-soft text-muted hover:text-fg"
            }`}
            key={item.id}
            onClick={() => {
              setIcon(item.id);
              setSaved(true);
              void applyAppIcon(item.id);
            }}
            role="radio"
            type="button"
          >
            <img alt="" className="size-14 rounded-[22%]" src={item.src} />
            {item.label}
          </button>
        ))}
      </div>
      {saved && (
        <p className="mt-2 text-xs text-success" role="status">
          Ícone salvo. {isIphone ? "Siga os passos abaixo para ele aparecer no iPhone." : "As próximas notificações já saem com ele."}
        </p>
      )}
      <div className="mt-3 rounded-xl border border-line-soft bg-surface-inset p-3 text-xs leading-5 text-fg-2">
        <p className="font-semibold text-fg">No iPhone</p>
        <p className="mt-1 text-muted">
          O iPhone usa nas notificações o ícone que o app tinha quando foi adicionado à tela de início. Para trocar:
        </p>
        <ol className="mt-1 list-decimal space-y-0.5 pl-5">
          <li>Escolha o ícone acima e toque em <b>Copiar link de instalação</b>.</li>
          <li>Segure o ícone do Flash na tela de início → <b>Remover app</b>.</li>
          <li>Cole o link no <b>Safari</b> → <b>Compartilhar</b> → <b>Adicionar à Tela de Início</b>.</li>
          <li>Abra o Flash pela tela de início, entre na conta e ative as notificações de novo aqui em Configurações.</li>
        </ol>
        <button
          className="btn-secondary mt-2 !min-h-9 text-xs"
          disabled={!icon}
          onClick={() => {
            const link = `${window.location.origin}/?icon=${icon ?? "dark"}`;
            void copyText(link).then(
              () => setCopiedLink(true),
              () => window.prompt("Copie o link:", link),
            );
          }}
          type="button"
        >
          {copiedLink ? "Link copiado ✓" : "Copiar link de instalação"}
        </button>
      </div>
    </section>
  );
}

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
  { id: "claro", label: "Claro", swatch: "linear-gradient(180deg,#ffffff,#f6f0ff 55%,#ece2ff)", text: "#17082e" },
  { id: "escuro", label: "Escuro", swatch: "linear-gradient(180deg,#0e0f16,#161322 55%,#211836)", text: "#fff" },
  { id: "pb", label: "Preto e branco", swatch: "linear-gradient(180deg,#000000,#0b0b0b 55%,#1a1a1a)", text: "#fff" },
  { id: "roxo", label: "Roxo", swatch: "linear-gradient(180deg,#8f1dff,#7a00ff 55%,#5b00c4)", text: "#fff" },
  {
    id: "galaxia",
    label: "Galáxia",
    swatch:
      "radial-gradient(1px 1px at 20% 30%,#fff,transparent),radial-gradient(1px 1px at 70% 20%,#fff,transparent),radial-gradient(1px 1px at 45% 70%,#fff,transparent),linear-gradient(180deg,#05041a,#1d0b4a 55%,#4a1592)",
    text: "#fff",
  },
  { id: "rosa", label: "Rosa", swatch: "linear-gradient(180deg,#ff5fb0,#ec2a8a 55%,#b0136a)", text: "#fff" },
  {
    id: "flores",
    label: "Flores 🌸",
    swatch:
      "radial-gradient(circle at 82% 22%,#ff8fbf 0 5px,transparent 6px),radial-gradient(circle at 70% 70%,#ffb3d1 0 4px,transparent 5px),linear-gradient(180deg,#fff7fa,#ffe6f0 55%,#ffd3e4)",
    text: "#5a1236",
  },
];

function IphoneWidgetCard() {
  const isAdmin = useAuth().user?.role === "SUPER_ADMIN";
  const [copied, setCopied] = useState(false);
  const [theme, setTheme] = useState<WidgetTheme>("roxo");
  // The look is saved on the account: a tap here changes the installed widget on its next
  // refresh, with no script to copy again.
  const savedTheme = useQuery({
    queryKey: ["widget-theme"],
    queryFn: () => apiRequest<{ theme: WidgetTheme | null }>("/api/widget/theme"),
  });
  useEffect(() => {
    if (savedTheme.data?.theme) setTheme(savedTheme.data.theme);
  }, [savedTheme.data?.theme]);
  const requestUpdate = useMutation({
    mutationFn: () => apiRequest<{ requested: boolean }>("/api/widget/update", { method: "POST" }),
  });
  const pickTheme = useMutation({
    mutationFn: (next: WidgetTheme) =>
      apiRequest<{ theme: WidgetTheme }>("/api/widget/theme", { method: "PUT", body: { theme: next } }),
  });
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
        Faturamento total do dia, vendas (inclusive as da Shark), conversão dos Pix, visualizações do Flash Post e o gráfico do dia na tela inicial, pelo app gratuito Scriptable.
      </p>
      <ol className="mt-3 list-decimal space-y-1 pl-5 text-xs leading-5 text-fg-2">
        <li>Instale o <b>Scriptable</b> na App Store.</li>
        <li>Toque em <b>Copiar script</b> aqui, abra o Scriptable, toque em <b>+</b> e cole.</li>
        <li>Na tela inicial, segure um espaço vazio → <b>+</b> → Scriptable → escolha o tamanho → toque no widget e selecione o script.</li>
      </ol>
      <p className="mt-2 text-[11px] leading-5 text-muted">
        Médio e grande: total do dia em destaque, as linhas de vendas{isAdmin ? ", comissão e arrecadação" : ""}, conversão dos Pix gerados para pagos,
        visualizações do dia e gráfico. Pequeno: total, conversão e visualizações. Tela de bloqueio: logo, valor e número de vendas. Venda nova aparece com um selo verde; tocar no widget abre a versão animada. O iPhone decide quando
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
            onClick={() => { setTheme(item.id); setCopied(false); pickTheme.mutate(item.id); }}
            role="radio"
            style={{ background: item.swatch, color: item.text }}
            type="button"
          >
            {item.label}
          </button>
        ))}
      </div>
      <p className="mt-1.5 min-h-4 text-[11px]" role="status">
        {pickTheme.isPending ? (
          <span className="text-muted">Aplicando…</span>
        ) : pickTheme.isSuccess ? (
          <span className="text-success">Tema aplicado ✓ O widget já instalado muda sozinho na próxima atualização.</span>
        ) : pickTheme.isError ? (
          <span className="text-danger">Não foi possível salvar o tema. Toque de novo.</span>
        ) : (
          <span className="text-muted">Toque num tema para aplicar. No iPhone, também dá para trocar tocando no widget e escolhendo o tema.</span>
        )}
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          className="btn-primary"
          disabled={requestUpdate.isPending}
          onClick={() => requestUpdate.mutate()}
          type="button"
        >
          {requestUpdate.isPending ? "Enviando…" : requestUpdate.isSuccess ? "Atualização enviada ✓" : "Atualizar widget"}
        </button>
        <button className="btn-secondary" disabled={copying} onClick={() => void copy()} type="button">
          {copying ? "Preparando…" : copied ? "Script copiado ✓" : "Copiar script"}
        </button>
      </div>
      <p className="mt-1.5 text-[11px] text-muted" role="status">
        {requestUpdate.isSuccess ? (
          <span className="text-success">
            Pedido enviado. O widget baixa a versão nova e o tema sozinho na próxima atualização do iPhone; para ser na hora, toque no widget uma vez.
          </span>
        ) : requestUpdate.isError ? (
          <span className="text-danger">Não foi possível enviar. Toque de novo.</span>
        ) : (
          "Atualizar widget: o widget já instalado baixa sozinho a versão nova do script e o tema escolhido, sem copiar e colar. Copiar script: só para instalar pela primeira vez."
        )}
      </p>
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
        <AppIconPicker />
        <PushSwitch />
        {owner && <PastSalesCard />}
      </div>

      {owner && <IphoneWidgetCard />}

      {sections.map((section) => {
        const items = section.items.filter((item) => (owner || !item.owner) && (!item.superAdmin || user?.role === "SUPER_ADMIN"));
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
