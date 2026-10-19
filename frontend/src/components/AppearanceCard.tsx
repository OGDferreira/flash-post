import { useState, useSyncExternalStore } from "react";
import { Check, Palette, RotateCcw } from "lucide-react";

import { FlashBotLogo } from "@/components/FlashBotLogo";
import {
  DEFAULT_ACCENT,
  accentPresets,
  getAccent,
  getFlashBotLogo,
  getGalaxy,
  getMotionOff,
  setAccent,
  setFlashBotLogo,
  setGalaxy,
  setMotionOff,
  subscribeAppearance,
  type FlashBotLogoStyle,
} from "@/lib/appearance";
import { applyTheme, getTheme } from "@/lib/theme";

/** Big selectable tile with a preview on top and a label below. */
function Choice({ active, onClick, preview, title, hint }: { active: boolean; onClick: () => void; preview: React.ReactNode; title: string; hint: string }) {
  return (
    <button
      aria-pressed={active}
      className={`relative flex flex-col overflow-hidden rounded-xl border text-left transition ${active ? "border-accent ring-2 ring-accent/40" : "border-line-soft hover:border-accent/60"}`}
      onClick={onClick}
      type="button"
    >
      <span className="grid h-24 place-items-center">{preview}</span>
      <span className="border-t border-line-soft px-3 py-2">
        <span className="block text-sm font-semibold text-fg">{title}</span>
        <span className="block text-[11px] text-muted">{hint}</span>
      </span>
      {active && <span className="absolute right-2 top-2 grid size-5 place-items-center rounded-full bg-brand text-white"><Check size={12} /></span>}
    </button>
  );
}

const galaxyPreview = (
  <span
    className="block h-full w-full"
    style={{
      background:
        "radial-gradient(60% 70% at 10% 50%, rgb(217 70 239 / .55), transparent 70%), radial-gradient(60% 70% at 95% 60%, rgb(14 165 233 / .5), transparent 70%), radial-gradient(1px 1px at 30% 30%, #fff, transparent), radial-gradient(1px 1px at 70% 20%, #fff, transparent), radial-gradient(1px 1px at 55% 75%, #fff, transparent), #05030d",
    }}
  />
);
const standardPreview = (
  <span
    className="block h-full w-full"
    style={{ background: "radial-gradient(70% 80% at 10% 0%, rgb(83 109 254 / .55), transparent 70%), radial-gradient(60% 70% at 90% 90%, rgb(150 70 255 / .3), transparent 70%), #05070f" }}
  />
);

/** Profile > Aparência: main color and "remover animações". Saved in this browser. */
export function AppearanceCard() {
  const [accent, setAccentState] = useState(getAccent);
  const [motionOff, setMotionState] = useState(getMotionOff);
  const galaxy = useSyncExternalStore(subscribeAppearance, getGalaxy);
  const logo = useSyncExternalStore(subscribeAppearance, getFlashBotLogo);

  const chooseGalaxy = (on: boolean) => {
    // The galaxy theme is a dark theme: turning it on leaves the light mode.
    if (on && getTheme() === "light") applyTheme("dark", true);
    setGalaxy(on, getTheme());
    if (!on) setAccent(getAccent(), getTheme());
  };
  const chooseLogo = (style: FlashBotLogoStyle) => setFlashBotLogo(style);

  const choose = (hex: string) => {
    setAccent(hex, getTheme());
    setAccentState(hex);
  };

  return (
    <section aria-label="Aparência" className="rounded-xl border border-line-soft bg-surface p-4 sm:p-5">
      <div className="flex items-center gap-2">
        <Palette className="text-accent" size={18} />
        <h2 className="text-base font-semibold text-fg">Aparência</h2>
      </div>
      <p className="mt-1 text-xs text-muted">Vale só para este navegador ou aparelho.</p>

      <div className="mt-4">
        <p className="text-sm font-medium text-fg-2">Tema</p>
        <div className="mt-2 grid grid-cols-2 gap-3 sm:max-w-md">
          <Choice active={!galaxy} hint="Escuro ou claro, com a cor que você escolher" onClick={() => chooseGalaxy(false)} preview={standardPreview} title="Padrão" />
          <Choice active={galaxy} hint="Escuro com nebulosa e neon azul, violeta e rosa" onClick={() => chooseGalaxy(true)} preview={galaxyPreview} title="Galáxia" />
        </div>
      </div>

      <div className="mt-5 border-t border-line-soft pt-4">
        <p className="text-sm font-medium text-fg-2">Logo do FlashBot</p>
        <div className="mt-2 grid grid-cols-2 gap-3 sm:max-w-md">
          {(["clean", "galaxy"] as const).map((style) => (
            <Choice
              active={logo === style}
              hint={style === "clean" ? "Mais simples e limpa" : "Com cores, brilho e textura"}
              key={style}
              onClick={() => chooseLogo(style)}
              preview={
                style === "clean" ? (
                  <svg className="size-14" viewBox="0 0 64 64"><rect fill="#3f8ff2" height="64" rx="16" width="64" /><path d="M24 9H51L48 17H32.4L30.8 23H45.5L42.6 31H31.5L16 57L21.5 37H15.5Z" fill="#fff" /></svg>
                ) : (
                  <img alt="" className="size-14 rounded-[22%]" src="/flashbot-logo-galaxy.png" />
                )
              }
              title={style === "clean" ? "Padrão" : "Galáxia"}
            />
          ))}
        </div>
        <p className="mt-2 flex items-center gap-2 text-[11px] text-muted">
          Agora no FlashBot: <FlashBotLogo className="size-5" />
        </p>
      </div>

      <div className="mt-5 border-t border-line-soft pt-4">
        <p className="text-sm font-medium text-fg-2">Cor do site {galaxy && <span className="text-xs font-normal text-muted">(o tema Galáxia usa as próprias cores)</span>}</p>
        <div className={`mt-2 flex-wrap items-center gap-2.5 ${galaxy ? "hidden" : "flex"}`}>
          {accentPresets.map((preset) => {
            const active = accent.toLowerCase() === preset.hex;
            return (
              <button
                aria-label={preset.name}
                aria-pressed={active}
                className="grid size-9 place-items-center rounded-full border border-line transition-transform hover:scale-110"
                key={preset.hex}
                onClick={() => choose(preset.hex)}
                style={{ background: preset.hex }}
                title={preset.name}
                type="button"
              >
                {active && <Check className="text-white" size={16} />}
              </button>
            );
          })}
          <label className="flex min-h-9 cursor-pointer items-center gap-2 rounded-full border border-line px-3 text-xs text-fg-2 hover:border-accent">
            Personalizada
            <input
              aria-label="Escolher outra cor"
              className="size-6 cursor-pointer rounded border-0 bg-transparent p-0"
              onChange={(event) => choose(event.target.value)}
              type="color"
              value={/^#[0-9a-f]{6}$/i.test(accent) ? accent : DEFAULT_ACCENT}
            />
          </label>
          <button className="btn-ghost btn-sm" onClick={() => choose(DEFAULT_ACCENT)} type="button">
            <RotateCcw size={14} />
            Padrão
          </button>
        </div>
      </div>

      <label className="mt-5 flex cursor-pointer items-center justify-between gap-4 border-t border-line-soft pt-4">
        <span>
          <span className="block text-sm font-medium text-fg-2">Remover animações</span>
          <span className="block text-xs text-muted">Desliga movimentos e transições do site.</span>
        </span>
        <input
          checked={motionOff}
          className="size-5 accent-[var(--brand-c)]"
          onChange={(event) => {
            setMotionOff(event.target.checked);
            setMotionState(event.target.checked);
          }}
          type="checkbox"
        />
      </label>
    </section>
  );
}
