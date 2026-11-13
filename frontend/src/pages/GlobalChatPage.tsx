import { useEffect, useMemo, useRef, useState } from "react";
import { ImagePlus, Loader2, SendHorizontal, Trash2 } from "lucide-react";

import { ApiError } from "@/services/api";
import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { confirmAction } from "@/lib/confirm";
import {
  type ChatMessage,
  useChatMessages,
  useDeleteMessage,
  useSendMessage,
  useSendPhoto,
} from "@/features/global-chat/api";

const MAX_IMAGE_BYTES = 2 * 1024 * 1024;

function timeLabel(iso: string): string {
  const date = new Date(iso);
  return date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function initial(nickname: string): string {
  return nickname.trim().charAt(0).toUpperCase() || "?";
}

export function GlobalChatPage() {
  const messages = useChatMessages();
  const sendMessage = useSendMessage();
  const sendPhoto = useSendPhoto();
  const deleteMessage = useDeleteMessage();

  const [draft, setDraft] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const items = useMemo(() => messages.data?.items ?? [], [messages.data]);

  // Stick to the newest message as the list grows.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [items.length]);

  const submit = async () => {
    const text = draft.trim();
    if (!text || sendMessage.isPending) return;
    setNotice(null);
    try {
      await sendMessage.mutateAsync(text);
      setDraft("");
    } catch (error) {
      setNotice(error instanceof ApiError ? error.message : "Não foi possível enviar.");
    }
  };

  const onPickPhoto = async (file: File | undefined) => {
    if (!file) return;
    setNotice(null);
    if (file.size > MAX_IMAGE_BYTES) {
      setNotice("A imagem deve ter até 2 MB.");
      return;
    }
    try {
      await sendPhoto.mutateAsync({ file, caption: draft });
      setDraft("");
    } catch (error) {
      setNotice(error instanceof ApiError ? error.message : "Não foi possível enviar a imagem.");
    } finally {
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const remove = async (message: ChatMessage) => {
    const ok = await confirmAction({
      title: "Apagar mensagem?",
      message: "A mensagem será removida do chat para todos.",
      confirmLabel: "Apagar",
      danger: true,
    });
    if (!ok) return;
    await deleteMessage.mutateAsync(message.id).catch(() => undefined);
  };

  return (
    <div className="mx-auto flex h-[calc(100dvh-7rem)] w-full max-w-3xl flex-col">
      <header className="mb-3">
        <h1 className="text-xl font-semibold text-fg">Chat global</h1>
        <p className="mt-1 text-sm text-muted">
          Converse com os outros usuários da plataforma. As mensagens somem após 36h e não é
          permitido compartilhar telefone, @ ou contatos.
        </p>
      </header>

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-line bg-surface">
        <div className="flex-1 space-y-3 overflow-y-auto px-3 py-4 sm:px-4">
          {messages.isPending ? (
            <LoadingState label="Carregando o chat" />
          ) : messages.error ? (
            <ErrorState
              message="Não foi possível carregar o chat."
              onRetry={() => void messages.refetch()}
            />
          ) : items.length === 0 ? (
            <EmptyState message="Nenhuma mensagem ainda. Seja o primeiro a falar!" />
          ) : (
            items.map((message) => (
              <ChatBubble key={message.id} message={message} onDelete={() => void remove(message)} />
            ))
          )}
          <div ref={bottomRef} />
        </div>

        {notice && (
          <div className="border-t border-line bg-danger-soft/60 px-4 py-2 text-xs text-danger">
            {notice}
          </div>
        )}

        <div className="flex items-end gap-2 border-t border-line bg-surface-inset/40 px-3 py-3 sm:px-4">
          <input
            ref={fileRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            className="hidden"
            onChange={(event) => void onPickPhoto(event.target.files?.[0])}
          />
          <button
            type="button"
            className="grid size-10 shrink-0 place-items-center rounded-xl border border-line text-muted hover:text-accent disabled:opacity-50"
            onClick={() => fileRef.current?.click()}
            disabled={sendPhoto.isPending}
            aria-label="Enviar foto"
          >
            {sendPhoto.isPending ? <Loader2 className="animate-spin" size={18} /> : <ImagePlus size={18} />}
          </button>
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void submit();
              }
            }}
            rows={1}
            maxLength={1000}
            placeholder="Escreva uma mensagem…"
            className="max-h-32 min-h-10 flex-1 resize-none rounded-xl border border-line bg-surface px-3 py-2 text-sm text-fg outline-none placeholder:text-muted focus:border-accent"
          />
          <button
            type="button"
            className="grid size-10 shrink-0 place-items-center rounded-xl bg-accent text-white hover:opacity-90 disabled:opacity-50"
            onClick={() => void submit()}
            disabled={!draft.trim() || sendMessage.isPending}
            aria-label="Enviar"
          >
            {sendMessage.isPending ? <Loader2 className="animate-spin" size={18} /> : <SendHorizontal size={18} />}
          </button>
        </div>
      </div>
    </div>
  );
}

function ChatBubble({ message, onDelete }: { message: ChatMessage; onDelete: () => void }) {
  const mine = message.is_mine;
  return (
    <div className={`flex gap-2 ${mine ? "flex-row-reverse" : "flex-row"}`}>
      {!mine && (
        <div className="grid size-8 shrink-0 place-items-center overflow-hidden rounded-full bg-surface-inset text-xs font-semibold text-accent">
          {message.author_avatar_url ? (
            <img src={message.author_avatar_url} alt="" className="size-full object-cover" />
          ) : (
            initial(message.author_nickname)
          )}
        </div>
      )}
      <div className={`group max-w-[78%] ${mine ? "items-end text-right" : "items-start"}`}>
        {!mine && (
          <p className="mb-0.5 px-1 text-xs font-medium text-muted">{message.author_nickname}</p>
        )}
        <div
          className={`relative inline-block rounded-2xl px-3 py-2 text-sm ${
            mine ? "bg-accent text-white" : "bg-surface-inset text-fg"
          }`}
        >
          {message.has_image && message.image_url && (
            <img
              src={message.image_url}
              alt="Imagem"
              className="mb-1 max-h-72 rounded-lg object-contain"
              loading="lazy"
            />
          )}
          {message.body && <p className="whitespace-pre-wrap break-words">{message.body}</p>}
          <span className={`mt-1 block text-[10px] ${mine ? "text-white/70" : "text-muted"}`}>
            {timeLabel(message.created_at)}
          </span>
          {message.can_delete && (
            <button
              type="button"
              onClick={onDelete}
              className="absolute -top-2 -left-2 hidden size-6 place-items-center rounded-full border border-line bg-surface text-muted hover:text-danger group-hover:grid"
              aria-label="Apagar"
            >
              <Trash2 size={12} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default GlobalChatPage;
