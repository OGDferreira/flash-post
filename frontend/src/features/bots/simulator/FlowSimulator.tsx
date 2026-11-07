import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CreditCard, ExternalLink, Hourglass, Play, QrCode, RotateCcw, UserX, X } from "lucide-react";

import { apiRequest } from "@/services/api";
import { useBotMedia } from "../editor/MediaGrid";
import type { ButtonStyle, FlowDefinition } from "../types";
import { simulate, type SimButton, type SimMessage } from "./simulate";

const ALLOWED = new Set(["B", "STRONG", "I", "EM", "U", "INS", "S", "STRIKE", "DEL", "CODE", "PRE", "A", "BLOCKQUOTE", "TG-SPOILER", "SPAN", "BR"]);

/** The owner's Telegram HTML, reduced to the tags Telegram shows (anything else becomes text). */
function safeHtml(html: string): string {
  if (typeof DOMParser === "undefined") return html.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c] ?? c);
  const doc = new DOMParser().parseFromString(`<div>${html}</div>`, "text/html");
  const clean = (node: Node, out: Node) => {
    node.childNodes.forEach((child) => {
      if (child.nodeType === Node.TEXT_NODE) {
        out.appendChild(document.createTextNode(child.textContent ?? ""));
        return;
      }
      if (child.nodeType !== Node.ELEMENT_NODE) return;
      const el = child as Element;
      if (!ALLOWED.has(el.tagName)) {
        clean(el, out);
        return;
      }
      const copy = document.createElement(el.tagName === "TG-SPOILER" ? "span" : el.tagName.toLowerCase());
      if (el.tagName === "A") {
        const href = el.getAttribute("href") ?? "";
        if (/^https?:\/\//i.test(href)) copy.setAttribute("href", href);
        copy.setAttribute("target", "_blank");
        copy.setAttribute("rel", "noreferrer");
      }
      if (el.tagName === "TG-SPOILER" || (el.tagName === "SPAN" && el.classList.contains("tg-spoiler"))) {
        copy.setAttribute("class", "sim-spoiler");
      }
      clean(el, copy);
      out.appendChild(copy);
    });
  };
  const wrapper = document.createElement("div");
  clean(doc.body.firstChild as Node, wrapper);
  return wrapper.innerHTML;
}

function Media({ id, spoiler }: { id: string; spoiler?: boolean }) {
  const library = useBotMedia();
  const item = library.data?.media.find((media) => media.id === id);
  const preview = useQuery({
    queryKey: ["bots", "media", "preview", id],
    queryFn: () => apiRequest<{ url: string }>(`/api/bots/media/${id}/preview`),
    enabled: Boolean(item) && item?.kind !== "audio",
    retry: false,
    staleTime: 50 * 60_000,
  });
  const url = preview.data?.url;
  const blur = spoiler ? "blur-xl" : "";
  return (
    <div className="relative aspect-square overflow-hidden rounded-lg bg-black/30">
      {item?.kind === "audio" ? (
        <div className="grid size-full place-items-center text-[11px] text-white/70">🎤 áudio</div>
      ) : url && item?.kind === "video" ? (
        <video className={`size-full object-cover ${blur}`} muted playsInline preload="metadata" src={`${url}#t=0.5`} />
      ) : url ? (
        <img alt="" className={`size-full object-cover ${blur}`} loading="lazy" src={url} />
      ) : (
        <div className="grid size-full place-items-center text-[10px] text-white/60">{item ? "carregando…" : "mídia removida"}</div>
      )}
      {spoiler && <span className="absolute inset-0 grid place-items-center text-[10px] font-semibold text-white">spoiler</span>}
    </div>
  );
}

const STYLE: Record<ButtonStyle, string> = {
  default: "bg-[#2b5278] text-white",
  primary: "bg-[#3390ec] text-white",
  success: "bg-[#31b545] text-white",
  danger: "bg-[#e53935] text-white",
};

function Bubble({ message, onTap, onCopy }: { message: SimMessage; onTap: (action: string) => void; onCopy: () => void }) {
  if (message.from === "note") {
    return (
      <p className="mx-auto max-w-[90%] rounded-full bg-black/35 px-3 py-1 text-center text-[11px] text-white/85">{message.text}</p>
    );
  }
  if (message.from === "user") {
    return (
      <div className="ml-auto max-w-[80%] rounded-2xl rounded-br-md bg-[#2b5278] px-3 py-2 text-sm text-white">{message.text}</div>
    );
  }
  const media = message.media ?? [];
  return (
    <div className="max-w-[88%] space-y-1">
      <div className="overflow-hidden rounded-2xl rounded-bl-md bg-[#182533] text-sm text-white">
        {message.qr && (
          <div className="mx-auto mt-2 grid aspect-square w-40 place-items-center rounded-lg bg-white text-black">
            <div className="text-center">
              <QrCode className="mx-auto" size={64} />
              <p className="mt-1 text-[10px] font-semibold">QR Code do Pix (simulado)</p>
            </div>
          </div>
        )}
        {media.length > 0 && (
          <div className={`grid gap-1 p-1 ${media.length > 1 ? "grid-cols-2" : ""}`}>
            {media.slice(0, 4).map((id) => <Media id={id} key={id} spoiler={message.spoiler} />)}
          </div>
        )}
        {(message.text || message.code) && (
          <div className="space-y-2 whitespace-pre-wrap break-words px-3 py-2 [&_a]:text-[#6ab2f2] [&_a]:underline [&_blockquote]:border-l-2 [&_blockquote]:border-[#6ab2f2] [&_blockquote]:pl-2 [&_code]:rounded [&_code]:bg-black/30 [&_code]:px-1 [&_.sim-spoiler]:rounded [&_.sim-spoiler]:bg-white/40 [&_.sim-spoiler]:text-transparent">
            {message.text && <div dangerouslySetInnerHTML={{ __html: safeHtml(message.text) }} />}
            {message.code && (
              <button
                className="block w-full break-all rounded-lg bg-black/35 p-2 text-left font-mono text-[11px] text-[#9fd3ff]"
                onClick={onCopy}
                title="Toque para copiar (simulado)"
                type="button"
              >
                {message.code}
              </button>
            )}
          </div>
        )}
      </div>
      {message.buttons?.map((row, index) => (
        <div className="flex gap-1" key={index}>
          {row.map((button: SimButton, j) => (
            <button
              className={`flex min-h-9 flex-1 items-center justify-center gap-1 rounded-lg px-2 text-xs font-medium ${STYLE[button.style ?? "default"]} ${button.action || button.copy ? "active:opacity-80" : "opacity-90"}`}
              key={j}
              onClick={() => {
                if (button.action) onTap(button.action);
                else if (button.copy) onCopy();
                else if (button.url) window.open(button.url, "_blank", "noopener");
              }}
              type="button"
            >
              {button.label}
              {button.url && <ExternalLink size={11} />}
            </button>
          ))}
        </div>
      ))}
    </div>
  );
}

/** Test the funnel: a Telegram-like chat that runs the funnel being edited, with simulated
 *  payment. Nothing real happens: no Pix, no charge, no message on Telegram. */
export function FlowSimulator({ flow, onClose }: { flow: FlowDefinition; onClose?: () => void }) {
  const [actions, setActions] = useState<string[]>(["start"]);
  const [toast, setToast] = useState<string | null>(null);
  const result = useMemo(() => simulate(flow, actions), [flow, actions]);
  const end = useRef<HTMLDivElement>(null);
  const tap = (action: string) => setActions((current) => [...current, action]);

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [actions.length]);
  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 1800);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const { controls } = result;
  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-[28px] border border-line bg-[#0e1621] shadow-2xl">
      <header className="flex items-center gap-2 border-b border-white/10 bg-[#17212b] px-3 py-2.5 text-white">
        <span className="grid size-9 place-items-center rounded-full bg-[#3390ec] text-sm font-bold">B</span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold">Teste do funil</p>
          <p className="text-[11px] text-white/60">simulação · nada é cobrado nem enviado</p>
        </div>
        <button
          aria-label="Reiniciar o teste"
          className="grid size-9 place-items-center rounded-full hover:bg-white/10"
          onClick={() => setActions(["start"])}
          title="Reiniciar"
          type="button"
        >
          <RotateCcw size={17} />
        </button>
        {onClose && (
          <button aria-label="Fechar o teste" className="grid size-9 place-items-center rounded-full hover:bg-white/10" onClick={onClose} type="button">
            <X size={18} />
          </button>
        )}
      </header>

      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto overscroll-contain bg-[#0e1621] bg-[radial-gradient(circle_at_20%_10%,rgba(51,144,236,.08),transparent_40%)] p-3">
        {result.messages.map((message, index) => (
          <Bubble key={index} message={message} onCopy={() => setToast("Código Pix copiado (simulado)")} onTap={tap} />
        ))}
        {!flow.plans.length && <p className="text-center text-[11px] text-white/60">Cadastre um plano para testar a compra.</p>}
        <div ref={end} />
      </div>

      {toast && <p className="mx-3 mb-2 rounded-lg bg-black/70 px-3 py-1.5 text-center text-xs text-white">{toast}</p>}

      <footer className="space-y-2 border-t border-white/10 bg-[#17212b] p-2.5">
        <div className="flex flex-wrap gap-1.5">
          {controls.canPay && (
            <button className="inline-flex min-h-9 flex-1 items-center justify-center gap-1.5 rounded-lg bg-[#31b545] px-3 text-xs font-semibold text-white" onClick={() => tap("pay")} type="button">
              <CreditCard size={14} /> Simular pagamento
            </button>
          )}
          {controls.canExpire && (
            <button className="inline-flex min-h-9 flex-1 items-center justify-center gap-1.5 rounded-lg bg-white/10 px-3 text-xs font-medium text-white" onClick={() => tap("expire")} type="button">
              <Hourglass size={14} /> Pix não pago (downsell)
            </button>
          )}
          {controls.canSkipNoPix && (
            <button className="inline-flex min-h-9 flex-1 items-center justify-center gap-1.5 rounded-lg bg-white/10 px-3 text-xs font-medium text-white" onClick={() => tap("nopix")} type="button">
              <UserX size={14} /> Lead não gerou Pix
            </button>
          )}
          {!controls.canPay && !controls.canSkipNoPix && (
            <button className="inline-flex min-h-9 flex-1 items-center justify-center gap-1.5 rounded-lg bg-white/10 px-3 text-xs font-medium text-white" onClick={() => setActions(["start"])} type="button">
              <Play size={14} /> Testar de novo
            </button>
          )}
        </div>
        <p className="text-center text-[10px] text-white/50">Toque nos botões das mensagens como o lead faria. As mudanças no editor aparecem aqui na hora.</p>
      </footer>
    </div>
  );
}
