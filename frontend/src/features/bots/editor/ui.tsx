import type { ReactNode } from "react";

import type { ButtonStyle } from "../types";

export function Field({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <label className="grid gap-1.5 text-sm text-fg-2">
      <span>{label}</span>
      {children}
      {hint && <span className="text-xs leading-5 text-muted">{hint}</span>}
    </label>
  );
}

export function Panel({
  icon,
  title,
  description,
  aside,
  children,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  aside?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <section className="space-y-4 rounded-2xl border border-line bg-surface p-4 sm:p-5">
      <div className="flex items-start gap-3">
        {icon && <span className="mt-0.5 shrink-0 text-accent">{icon}</span>}
        <div className="min-w-0 flex-1">
          <h3 className="font-medium text-fg">{title}</h3>
          {description && <p className="mt-0.5 text-sm leading-6 text-muted">{description}</p>}
        </div>
        {aside && <div className="shrink-0">{aside}</div>}
      </div>
      {children}
    </section>
  );
}

export function Switch({ checked, onChange, label }: { checked: boolean; onChange: (value: boolean) => void; label: string }) {
  return (
    <button
      aria-checked={checked}
      aria-label={label}
      className={`relative inline-flex h-7 w-12 shrink-0 items-center rounded-full transition-colors ${checked ? "bg-brand" : "bg-well"}`}
      onClick={() => onChange(!checked)}
      role="switch"
      type="button"
    >
      <span className={`inline-block size-5 rounded-full bg-white shadow transition-transform ${checked ? "translate-x-6" : "translate-x-1"}`} />
    </button>
  );
}

const styles: { value: ButtonStyle; label: string; className: string }[] = [
  { value: "default", label: "Padrão", className: "border-line bg-well text-fg" },
  { value: "primary", label: "Azul", className: "border-[#3b82f6]/50 bg-[#3b82f6]/15 text-[#7fb0ff]" },
  { value: "success", label: "Verde", className: "border-[#22c55e]/50 bg-[#22c55e]/15 text-[#6ee79a]" },
  { value: "danger", label: "Vermelho", className: "border-[#ef4444]/50 bg-[#ef4444]/15 text-[#ff8a8a]" },
];

/** Telegram button color (Telegram apps from Feb 2026; older ones show the default look). */
export function StylePicker({ value, onChange, label = "Cor do botão" }: { value: ButtonStyle; onChange: (value: ButtonStyle) => void; label?: string }) {
  return (
    <div className="grid gap-1.5 text-sm text-fg-2">
      <span>
        {label} <span className="text-xs text-muted">· cor no Telegram</span>
      </span>
      <div className="flex flex-wrap gap-2" role="radiogroup" aria-label={label}>
        {styles.map((item) => (
          <button
            aria-checked={value === item.value}
            className={`min-h-9 rounded-full border px-4 text-xs font-medium transition ${item.className} ${
              value === item.value ? "ring-2 ring-white/70" : "opacity-70"
            }`}
            key={item.value}
            onClick={() => onChange(item.value)}
            role="radio"
            type="button"
          >
            {item.label}
          </button>
        ))}
      </div>
    </div>
  );
}

const delayUnits = [
  { value: 1, label: "minutos" },
  { value: 60, label: "horas" },
  { value: 1440, label: "dias" },
];

/** Minutes stored, shown as minutes/hours/days. ``allowZero`` adds "Imediato". */
export function DelayInput({ value, onChange, allowZero = true }: { value: number; onChange: (minutes: number) => void; allowZero?: boolean }) {
  const unit = value > 0 && value % 1440 === 0 ? 1440 : value > 0 && value % 60 === 0 ? 60 : 1;
  const immediate = allowZero && value === 0;
  return (
    <div className="flex flex-wrap items-center gap-2">
      {allowZero && (
        <select
          aria-label="Quando enviar"
          className="field !w-auto"
          value={immediate ? "now" : "later"}
          onChange={(event) => onChange(event.target.value === "now" ? 0 : 10)}
        >
          <option value="now">Imediato</option>
          <option value="later">Depois de…</option>
        </select>
      )}
      {!immediate && (
        <>
          <input
            aria-label="Tempo de espera"
            className="field !w-24"
            min={1}
            type="number"
            value={Math.max(1, Math.round(value / unit))}
            onChange={(event) => onChange(Math.min(43200, Math.max(1, Number(event.target.value) || 1) * unit))}
          />
          <select
            aria-label="Unidade"
            className="field !w-auto"
            value={unit}
            onChange={(event) => onChange(Math.min(43200, Math.max(1, Math.round(value / unit)) * Number(event.target.value)))}
          >
            {delayUnits.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </>
      )}
    </div>
  );
}

export function MoneyInput({ value, onChange, label = "Preço (R$)" }: { value: string; onChange: (value: string) => void; label?: string }) {
  return (
    <Field label={label}>
      <input
        className="field"
        inputMode="decimal"
        value={value}
        onChange={(event) => onChange(event.target.value.replace(/[^\d.,]/g, ""))}
      />
    </Field>
  );
}

const durations: { value: number | null; label: string }[] = [
  { value: 7, label: "Semanal" },
  { value: 15, label: "Quinzenal" },
  { value: 30, label: "Mensal" },
  { value: 90, label: "Trimestral" },
  { value: 180, label: "Semestral" },
  { value: 365, label: "Anual" },
  { value: null, label: "Vitalício" },
];

export function DurationSelect({ value, onChange }: { value: number | null; onChange: (days: number | null) => void }) {
  const preset = durations.some((item) => item.value === value);
  return (
    <Field label="Duração do acesso">
      <div className="flex gap-2">
        <select
          className="field"
          value={preset ? String(value ?? "life") : "custom"}
          onChange={(event) => {
            const choice = event.target.value;
            onChange(choice === "life" ? null : choice === "custom" ? 10 : Number(choice));
          }}
        >
          {durations.map((item) => (
            <option key={item.label} value={item.value ?? "life"}>
              {item.label}
            </option>
          ))}
          <option value="custom">Dias personalizados</option>
        </select>
        {!preset && (
          <input
            aria-label="Dias"
            className="field !w-24"
            max={3650}
            min={1}
            type="number"
            value={value ?? 1}
            onChange={(event) => onChange(Math.min(3650, Math.max(1, Number(event.target.value) || 1)))}
          />
        )}
      </div>
    </Field>
  );
}

/** Collapsible card used by plans and sequence steps. */
export function Collapsible({
  title,
  subtitle,
  open,
  onToggle,
  actions,
  leading,
  children,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  open: boolean;
  onToggle: () => void;
  actions?: ReactNode;
  /** Before the title, e.g. a drag handle. */
  leading?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-line bg-surface-inset">
      <div className="flex items-center gap-2 p-3 sm:p-4">
        {leading}
        <button aria-expanded={open} className="flex min-w-0 flex-1 items-center gap-3 text-left" onClick={onToggle} type="button">
          <span className={`text-muted transition-transform ${open ? "rotate-90" : ""}`}>›</span>
          <span className="min-w-0">
            <span className="block truncate font-medium text-fg">{title}</span>
            {subtitle && <span className="block truncate text-xs text-muted">{subtitle}</span>}
          </span>
        </button>
        {actions}
      </div>
      {open && <div className="space-y-4 border-t border-line-soft p-3 sm:p-4">{children}</div>}
    </div>
  );
}
