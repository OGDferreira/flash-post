import { useRef } from "react";
import { Bold, Code, EyeOff, Italic, Quote, Strikethrough, Underline } from "lucide-react";

const tools = [
  { tag: "b", label: "Negrito", icon: Bold },
  { tag: "i", label: "Itálico", icon: Italic },
  { tag: "u", label: "Sublinhado", icon: Underline },
  { tag: "s", label: "Riscado", icon: Strikethrough },
  { tag: "code", label: "Código (toque para copiar)", icon: Code },
  { tag: "tg-spoiler", label: "Spoiler (texto escondido)", icon: EyeOff },
  { tag: "blockquote", label: "Citação", icon: Quote },
] as const;

export const BASE_VARIABLES = ["{nome}", "{username}", "{saudacao}", "{bot.nome}", "{bot.username}"];

/**
 * Plain textarea with Telegram formatting: the toolbar wraps the selection in
 * the HTML tags Telegram understands (the server re-validates them on send).
 */
export function RichTextEditor({
  label,
  value,
  onChange,
  variables = BASE_VARIABLES,
  max = 4000,
  rows = 6,
  required,
  hint,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  variables?: string[];
  max?: number;
  rows?: number;
  required?: boolean;
  hint?: string;
}) {
  const area = useRef<HTMLTextAreaElement>(null);

  const apply = (before: string, after = "") => {
    const element = area.current;
    if (!element) return;
    const { selectionStart: start, selectionEnd: end } = element;
    const next = value.slice(0, start) + before + value.slice(start, end) + after + value.slice(end);
    onChange(next.slice(0, max));
    requestAnimationFrame(() => {
      element.focus();
      // Keep the wrapped text selected (or the cursor between the tags when nothing was selected).
      element.setSelectionRange(start + before.length, end + before.length);
    });
  };

  return (
    <div className="grid gap-2 text-sm text-fg-2">
      <span>
        {label} {required && <span className="text-danger">*</span>}
      </span>
      <div className="overflow-hidden rounded-xl border border-line bg-surface-inset focus-within:border-brand">
        <div className="flex flex-wrap gap-0.5 border-b border-line-soft p-1.5" role="toolbar" aria-label="Formatação">
          {tools.map(({ tag, label: toolLabel, icon: Icon }) => (
            <button
              aria-label={toolLabel}
              className="grid size-9 place-items-center rounded-lg text-muted hover:bg-well hover:text-fg"
              key={tag}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => apply(`<${tag}>`, `</${tag}>`)}
              title={toolLabel}
              type="button"
            >
              <Icon size={16} />
            </button>
          ))}
        </div>
        <textarea
          aria-label={label}
          className="block w-full resize-y bg-transparent p-3 text-sm leading-6 text-fg outline-none"
          maxLength={max}
          ref={area}
          rows={rows}
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs text-muted">{hint}</span>
        <span className={`text-xs ${value.length > max * 0.95 ? "text-warning" : "text-muted"}`}>
          {value.length}/{max} caracteres
        </span>
      </div>
      {variables.length > 0 && (
        <div className="space-y-1.5">
          <span className="text-xs text-muted">Variáveis (toque para inserir)</span>
          <div className="flex flex-wrap gap-1.5">
            {variables.map((variable) => (
              <button
                className="rounded-lg border border-line bg-well px-2.5 py-1.5 font-mono text-xs text-fg-2 hover:border-brand"
                key={variable}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => apply(variable)}
                type="button"
              >
                {variable}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
