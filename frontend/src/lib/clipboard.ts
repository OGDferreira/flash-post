/** Copy prepared text during the click, with a fallback for browsers without Clipboard API. */
export async function copyText(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch { /* Try the selected-text fallback; callers also offer manual copying. */ }
  }
  const previous = document.activeElement as HTMLElement | null;
  const field = document.createElement("textarea");
  field.value = text;
  field.readOnly = true;
  field.style.cssText = "position:fixed;top:0;left:0;opacity:0;font-size:16px";
  document.body.appendChild(field);
  try {
    field.focus();
    field.select();
    field.setSelectionRange(0, text.length);
    if (!document.execCommand("copy")) throw new Error("Selecione o script abaixo e copie manualmente.");
  } finally {
    field.remove();
    previous?.focus();
  }
}

/** Safari requires clipboard.write to start before awaiting the token request. */
export function copyGeneratedText(text: Promise<string>): Promise<void> {
  if (navigator.clipboard?.write && typeof ClipboardItem !== "undefined") {
    return navigator.clipboard.write([new ClipboardItem({
      "text/plain": text.then((value) => new Blob([value], { type: "text/plain" })),
    })]);
  }
  return text.then(copyText);
}
