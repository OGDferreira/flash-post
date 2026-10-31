import { useEffect, useRef, useState } from "react";

/**
 * "Custom letters" for Telegram copy: Unicode look-alike alphabets (𝐁𝐨𝐥𝐝, 𝓢𝓬𝓻𝓲𝓹𝓽…). They are
 * plain characters, so Telegram shows them anywhere with no library or special bot.
 * Accents stay as combining marks, and HTML tags and {variables} are left untouched.
 */
type FontStyle = {
  id: string;
  label: string;
  upper: number | string;
  lower: number | string;
  digit?: number;
  exceptions?: Record<string, string>;
};

const SMALL_CAPS = "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ";

export const FONT_STYLES: FontStyle[] = [
  { id: "bold", label: "Negrito", upper: 0x1d400, lower: 0x1d41a, digit: 0x1d7ce },
  { id: "italic", label: "Itálico", upper: 0x1d434, lower: 0x1d44e, exceptions: { h: "ℎ" } },
  { id: "bold-italic", label: "Negrito itálico", upper: 0x1d468, lower: 0x1d482 },
  { id: "sans-bold", label: "Negrito moderno", upper: 0x1d5d4, lower: 0x1d5ee, digit: 0x1d7ec },
  { id: "sans-bold-italic", label: "Moderno itálico", upper: 0x1d63c, lower: 0x1d656 },
  { id: "script", label: "Cursiva", upper: 0x1d4d0, lower: 0x1d4ea },
  { id: "gothic", label: "Gótica", upper: 0x1d56c, lower: 0x1d586 },
  {
    id: "double",
    label: "Contorno",
    upper: 0x1d538,
    lower: 0x1d552,
    digit: 0x1d7d8,
    exceptions: { C: "ℂ", H: "ℍ", N: "ℕ", P: "ℙ", Q: "ℚ", R: "ℝ", Z: "ℤ" },
  },
  { id: "mono", label: "Máquina", upper: 0x1d670, lower: 0x1d68a, digit: 0x1d7f6 },
  // capitals stay as they are; lowercase becomes small capitals
  { id: "small-caps", label: "Versalete", upper: 0x41, lower: SMALL_CAPS },
  { id: "circled", label: "Círculos", upper: 0x24b6, lower: 0x24d0 },
];

function mapChar(char: string, style: FontStyle): string {
  if (style.exceptions?.[char]) return style.exceptions[char];
  const code = char.charCodeAt(0);
  if (code >= 65 && code <= 90) {
    if (typeof style.upper === "string") return [...style.upper][code - 65] ?? char;
    return String.fromCodePoint(style.upper + code - 65);
  }
  if (code >= 97 && code <= 122) {
    if (typeof style.lower === "string") return [...style.lower][code - 97] ?? char;
    return String.fromCodePoint(style.lower + code - 97);
  }
  if (code >= 48 && code <= 57 && style.digit) return String.fromCodePoint(style.digit + code - 48);
  return char;
}

/** Restyle the letters of ``text``, keeping HTML tags, {variables} and accents intact. */
export function toFancy(text: string, style: FontStyle): string {
  return text
    .split(/(<[^>]*>|\{[^}]*\})/)
    .map((part) => (part.startsWith("<") || part.startsWith("{") ? part : [...part.normalize("NFD")].map((c) => mapChar(c, style)).join("")))
    .join("")
    .normalize("NFC");
}

/** "Aa" button: pick a style and the selected text (or the whole field) is converted. */
export function FontMenu({ onPick, compact = false }: { onPick: (style: FontStyle) => void; compact?: boolean }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (event: PointerEvent) => {
      if (!box.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);
  return (
    <div className="relative" ref={box}>
      <button
        aria-expanded={open}
        aria-label="Letras personalizadas"
        className={`grid place-items-center rounded-lg text-muted hover:bg-well hover:text-fg ${compact ? "h-full min-h-10 px-2.5" : "size-9"}`}
        onClick={() => setOpen((value) => !value)}
        onMouseDown={(event) => event.preventDefault()}
        title="Letras personalizadas"
        type="button"
      >
        <span className="text-sm font-semibold">Aa</span>
      </button>
      {open && (
        <div className={`absolute z-30 mt-1 w-56 ${compact ? "right-0" : "left-0"} rounded-xl border border-line bg-surface p-1 shadow-lg`} role="menu">
          <p className="px-2 py-1 text-[11px] text-muted">Selecione o texto e escolha a letra</p>
          {FONT_STYLES.map((style) => (
            <button
              className="flex w-full items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-left text-sm text-fg hover:bg-well"
              key={style.id}
              onClick={() => {
                onPick(style);
                setOpen(false);
              }}
              onMouseDown={(event) => event.preventDefault()}
              role="menuitem"
              type="button"
            >
              <span>{toFancy("Flash Bot", style)}</span>
              <span className="text-[11px] text-muted">{style.label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
