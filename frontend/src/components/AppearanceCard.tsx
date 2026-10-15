import { useState } from "react";
import { Check, Palette, RotateCcw } from "lucide-react";

import {
  DEFAULT_ACCENT,
  accentPresets,
  getAccent,
  getMotionOff,
  setAccent,
  setMotionOff,
} from "@/lib/appearance";
import { getTheme } from "@/lib/theme";

/** Profile > Aparência: main color and "remover animações". Saved in this browser. */
export function AppearanceCard() {
  const [accent, setAccentState] = useState(getAccent);
  const [motionOff, setMotionState] = useState(getMotionOff);

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
        <p className="text-sm font-medium text-fg-2">Cor do site</p>
        <div className="mt-2 flex flex-wrap items-center gap-2.5">
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
