import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ImagePlus, Mic, Search, Send } from "lucide-react";

import { ApiError, apiRequest } from "@/services/api";
import type { BotMedia, ChatMessage, Conversation, ConversationDetail } from "./types";

const timeLabel = (iso: string | null) => {
  if (!iso) return "";
  const date = new Date(iso);
  const today = new Date();
  const sameDay = date.toDateString() === today.toDateString();
  return date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) +
    (sameDay ? "" : ` · ${date.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })}`);
};

const KIND_LABEL: Record<ChatMessage["kind"], string> = {
  text: "", photo: "🖼 Imagem", video: "🎞 Vídeo", voice: "🎤 Áudio", audio: "🎵 Áudio",
  video_note: "🎥 Vídeo", document: "📎 Arquivo", sticker: "🌟 Figurinha", other: "📎 Mídia",
};

/** Live-chat inbox: pick a lead, read its conversation with the bot, and reply. */
export function ConversationsPanel() {
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const list = useQuery({
    queryKey: ["bots", "conversations", search],
    queryFn: () => apiRequest<{ conversations: Conversation[] }>(`/api/bots/conversations?q=${encodeURIComponent(search)}`),
    refetchInterval: 15_000,
  });
  const conversations = list.data?.conversations ?? [];

  return (
    <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
      <div className={`glass-panel flex max-h-[72vh] flex-col overflow-hidden p-0 ${selected ? "hidden lg:flex" : "flex"}`}>
        <div className="border-b border-line-soft p-3">
          <div className="flex items-center gap-2 rounded-lg border border-line bg-surface-inset px-2">
            <Search size={15} className="text-muted" />
            <input
              className="h-9 flex-1 bg-transparent text-sm text-fg outline-none"
              placeholder="Buscar lead por nome ou @"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {conversations.length === 0 && (
            <p className="p-4 text-sm text-muted">
              {list.isLoading ? "Carregando..." : "Nenhuma conversa ainda. Quando um lead falar com o bot, aparece aqui."}
            </p>
          )}
          {conversations.map((conversation) => (
            <button
              key={conversation.lead_id}
              type="button"
              onClick={() => setSelected(conversation.lead_id)}
              className={`flex w-full items-center gap-3 border-b border-line-soft px-3 py-2.5 text-left transition hover:bg-well ${
                selected === conversation.lead_id ? "bg-well" : ""
              }`}
            >
              <span className="grid size-10 shrink-0 place-items-center rounded-full bg-brand-soft text-sm font-semibold text-accent">
                {(conversation.name || "L").slice(0, 1).toUpperCase()}
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium text-fg">{conversation.name}</span>
                  <span className="shrink-0 text-[11px] text-muted">{timeLabel(conversation.last_at)}</span>
                </span>
                <span className="flex items-center justify-between gap-2">
                  <span className="truncate text-xs text-muted">{conversation.last_preview || (conversation.username ? `@${conversation.username}` : "")}</span>
                  {conversation.unread > 0 && (
                    <span className="grid h-5 min-w-5 shrink-0 place-items-center rounded-full bg-brand px-1.5 text-[11px] font-semibold text-white">
                      {conversation.unread}
                    </span>
                  )}
                </span>
              </span>
            </button>
          ))}
        </div>
      </div>

      <div className={`${selected ? "block" : "hidden lg:block"}`}>
        {selected ? (
          <Conversation leadId={selected} onBack={() => setSelected(null)} />
        ) : (
          <div className="glass-panel grid h-full min-h-[300px] place-items-center p-6 text-center text-sm text-muted">
            Escolha uma conversa à esquerda para ver as mensagens e responder.
          </div>
        )}
      </div>
    </div>
  );
}

function Conversation({ leadId, onBack }: { leadId: string; onBack: () => void }) {
  const cache = useQueryClient();
  const scroller = useRef<HTMLDivElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const [text, setText] = useState("");
  const [accept, setAccept] = useState("image/*");

  const convo = useQuery({
    queryKey: ["bots", "conversation", leadId],
    queryFn: () => apiRequest<ConversationDetail>(`/api/bots/conversations/${leadId}`),
    refetchInterval: 8_000,
  });

  // Clear the unread badge once the conversation is opened.
  useEffect(() => {
    apiRequest(`/api/bots/conversations/${leadId}/read`, { method: "POST" })
      .then(() => cache.invalidateQueries({ queryKey: ["bots", "conversations"] }))
      .catch(() => undefined);
  }, [leadId, cache]);

  const messages = convo.data?.messages ?? [];
  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight });
  }, [messages.length]);

  const refresh = () => {
    cache.invalidateQueries({ queryKey: ["bots", "conversation", leadId] });
    cache.invalidateQueries({ queryKey: ["bots", "conversations"] });
  };

  const sendText = useMutation({
    mutationFn: () => apiRequest(`/api/bots/conversations/${leadId}/reply`, { method: "POST", body: { text: text.trim() } }),
    onSuccess: () => {
      setText("");
      refresh();
    },
  });

  const sendMedia = useMutation({
    mutationFn: async (file: File) => {
      const media = await apiRequest<BotMedia>(`/api/bots/media?filename=${encodeURIComponent(file.name)}`, { method: "POST", body: file });
      return apiRequest(`/api/bots/conversations/${leadId}/reply`, { method: "POST", body: { media_id: media.id } });
    },
    onSuccess: refresh,
  });

  const lead = convo.data?.lead;
  const error = (sendText.error ?? sendMedia.error) instanceof ApiError
    ? (sendText.error ?? sendMedia.error as ApiError).message
    : null;
  const busy = sendText.isPending || sendMedia.isPending;

  return (
    <div className="glass-panel flex h-[72vh] flex-col overflow-hidden p-0">
      <header className="flex items-center gap-3 border-b border-line-soft p-3">
        <button type="button" onClick={onBack} className="btn-ghost !min-h-9 !px-2 lg:hidden" aria-label="Voltar">
          <ArrowLeft size={18} />
        </button>
        <span className="grid size-9 shrink-0 place-items-center rounded-full bg-brand-soft text-sm font-semibold text-accent">
          {(lead?.name || "L").slice(0, 1).toUpperCase()}
        </span>
        <span className="min-w-0">
          <span className="block truncate text-sm font-semibold text-fg">{lead?.name ?? "Lead"}</span>
          <span className="block truncate text-xs text-muted">
            {lead?.username ? `@${lead.username}` : ""}{lead?.bot ? ` · @${lead.bot}` : ""}
          </span>
        </span>
      </header>

      <div ref={scroller} className="min-h-0 flex-1 space-y-2 overflow-y-auto bg-well/40 p-3">
        {messages.length === 0 && !convo.isLoading && (
          <p className="py-6 text-center text-sm text-muted">Sem mensagens nesta conversa ainda.</p>
        )}
        {messages.map((message) => (
          <Bubble key={message.id} leadId={leadId} message={message} />
        ))}
      </div>

      {lead?.blocked ? (
        <p className="border-t border-line-soft p-3 text-center text-xs text-danger">
          Este lead bloqueou o bot — não dá para enviar mensagens.
        </p>
      ) : (
        <div className="border-t border-line-soft p-3">
          {error && <p className="mb-2 text-xs text-danger" role="alert">{error}</p>}
          <div className="flex items-end gap-2">
            <input
              ref={fileInput}
              type="file"
              accept={accept}
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0];
                event.target.value = "";
                if (file) sendMedia.mutate(file);
              }}
            />
            <button
              type="button"
              aria-label="Enviar imagem"
              disabled={busy}
              onClick={() => { setAccept("image/jpeg,image/png,image/webp,video/mp4"); setTimeout(() => fileInput.current?.click(), 0); }}
              className="btn-ghost !min-h-10 !px-2.5 disabled:opacity-50"
            >
              <ImagePlus size={18} />
            </button>
            <button
              type="button"
              aria-label="Enviar áudio"
              disabled={busy}
              onClick={() => { setAccept("audio/ogg,audio/mpeg,audio/mp4,.mp3,.m4a,.ogg,.opus"); setTimeout(() => fileInput.current?.click(), 0); }}
              className="btn-ghost !min-h-10 !px-2.5 disabled:opacity-50"
            >
              <Mic size={18} />
            </button>
            <textarea
              rows={1}
              value={text}
              disabled={busy}
              placeholder="Escreva uma mensagem…"
              onChange={(event) => setText(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  if (text.trim()) sendText.mutate();
                }
              }}
              className="max-h-28 min-h-10 flex-1 resize-none rounded-lg border border-line bg-surface-inset px-3 py-2 text-sm text-fg outline-none focus:border-brand"
            />
            <button
              type="button"
              aria-label="Enviar"
              disabled={busy || !text.trim()}
              onClick={() => sendText.mutate()}
              className="grid size-10 shrink-0 place-items-center rounded-lg bg-brand text-white disabled:opacity-50"
            >
              <Send size={17} />
            </button>
          </div>
          {sendMedia.isPending && <p className="mt-1.5 text-xs text-muted">Enviando arquivo…</p>}
        </div>
      )}
    </div>
  );
}

function Bubble({ leadId, message }: { leadId: string; message: ChatMessage }) {
  const outbound = message.direction === "out";
  const mediaUrl = `/api/bots/conversations/${leadId}/messages/${message.id}/media`;
  const align = outbound ? "ml-auto items-end" : "mr-auto items-start";
  const tint = outbound
    ? (message.from_operator ? "bg-brand text-white" : "bg-surface-inset text-fg-2")
    : "bg-surface text-fg";
  return (
    <div className={`flex max-w-[82%] flex-col gap-1 ${align}`}>
      <div className={`rounded-2xl px-3 py-2 text-sm ${tint}`}>
        {message.direction === "in" && message.has_media && <InboundMedia kind={message.kind} url={mediaUrl} />}
        {outbound && message.has_media && message.kind !== "text" && (
          <p className="text-xs opacity-80">{KIND_LABEL[message.kind] || "📎 Mídia"} enviada</p>
        )}
        {message.text && <p className="whitespace-pre-wrap break-words">{stripTags(message.text)}</p>}
        {!message.text && message.kind === "text" && <p className="opacity-60">—</p>}
      </div>
      <span className="px-1 text-[10px] text-muted">
        {outbound ? (message.from_operator ? "Você" : "Bot") : ""} {timeLabel(message.created_at)}
      </span>
    </div>
  );
}

function InboundMedia({ kind, url }: { kind: ChatMessage["kind"]; url: string }) {
  if (kind === "photo" || kind === "sticker") {
    return <img src={url} alt="" className="mb-1 max-h-64 rounded-lg object-contain" loading="lazy" />;
  }
  if (kind === "voice" || kind === "audio") {
    return <audio controls src={url} className="mb-1 w-56 max-w-full" />;
  }
  if (kind === "video" || kind === "video_note") {
    return <video controls src={url} className="mb-1 max-h-64 rounded-lg" />;
  }
  return (
    <a href={url} target="_blank" rel="noreferrer" className="mb-1 block text-xs font-medium underline">
      {KIND_LABEL[kind] || "📎 Mídia"} — abrir
    </a>
  );
}

/** The bot stores funnel copy as light HTML; show it as plain text in the chat bubbles. */
function stripTags(value: string): string {
  return value.replace(/<[^>]+>/g, "").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
}
