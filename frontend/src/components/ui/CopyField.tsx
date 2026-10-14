import { useEffect, useRef, useState } from "react";
import { Check, Copy } from "lucide-react";

/** Read-only value with a copy button (works without the Clipboard API). */
export function CopyField({
  label,
  value,
  mono = true,
  hint,
}: {
  label: string;
  value: string;
  mono?: boolean;
  hint?: string;
}) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  const copy = async () => {
    let ok = false;
    try {
      await navigator.clipboard.writeText(value);
      ok = true;
    } catch {
      // Fallback for browsers/contexts where the Clipboard API is blocked.
      const area = document.createElement("textarea");
      area.value = value;
      area.setAttribute("readonly", "");
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      try {
        ok = document.execCommand("copy");
      } catch {
        ok = false;
      }
      document.body.removeChild(area);
    }
    setState(ok ? "copied" : "failed");
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setState("idle"), 2200);
  };

  return (
    <div className="grid gap-1.5 text-sm text-[#cbd5e1]">
      <span>{label}</span>
      <div className="flex gap-2">
        <input
          aria-label={label}
          className={`field min-w-0 flex-1 !text-xs ${mono ? "font-mono" : ""}`}
          onFocus={(event) => event.currentTarget.select()}
          readOnly
          value={value}
        />
        <button className="btn-secondary shrink-0 !px-3" onClick={() => void copy()} type="button">
          {state === "copied" ? <Check size={15} /> : <Copy size={15} />}
          <span aria-live="polite">{state === "copied" ? "Copiado" : state === "failed" ? "Falhou" : "Copiar"}</span>
        </button>
      </div>
      {hint && <span className="text-xs leading-5 text-[#94a3b8]">{hint}</span>}
    </div>
  );
}
