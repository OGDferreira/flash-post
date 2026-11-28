import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, FileAudio, Film, Image as ImageIcon, Library, Pause, Play, Plus, RefreshCw, Trash2, Upload } from "lucide-react";

import { Modal } from "@/components/ui/Modal";
import { ApiError, apiRequest } from "@/services/api";
import type { BotMedia } from "../types";
import { useBotApi } from "./apiBase";

const ACCEPT: Record<BotMedia["kind"], string> = {
  photo: "image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp",
  // iPhone videos come as .MOV: same container as MP4, so they go up as MP4
  video: "video/mp4,video/quicktime,video/x-m4v,.mp4,.mov,.m4v",
  audio: "audio/ogg,audio/mpeg,audio/mp4,.ogg,.oga,.opus,.mp3,.m4a",
};

const TYPE_BY_EXTENSION: Record<string, string> = {
  jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png", webp: "image/webp",
  mp4: "video/mp4", mov: "video/mp4", m4v: "video/mp4",
  ogg: "audio/ogg", oga: "audio/ogg", opus: "audio/ogg", mp3: "audio/mpeg", m4a: "audio/mp4",
};

/** The type the server expects. Windows often reports no type at all, and iPhone .MOV
 * (QuickTime) is sent as MP4 with an .mp4 name so Telegram plays it as a video. */
function normalizeUpload(file: File): File {
  const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
  const quicktime = ["mov", "m4v", "qt"].includes(extension) || file.type === "video/quicktime" || file.type === "video/x-m4v";
  if (quicktime) return new File([file], file.name.replace(/\.(mov|m4v|qt)$/i, "") + ".mp4", { type: "video/mp4" });
  if (!file.type && TYPE_BY_EXTENSION[extension]) return new File([file], file.name, { type: TYPE_BY_EXTENSION[extension] });
  return file;
}

export function useBotMedia() {
  const api = useBotApi();
  return useQuery({
    queryKey: [...api.mediaKey],
    queryFn: () => apiRequest<{ media: BotMedia[] }>(api.mediaListUrl),
    retry: false,
    staleTime: 60_000,
  });
}

function usePreview(id: string, enabled: boolean) {
  const api = useBotApi();
  return useQuery({
    queryKey: [...api.mediaKey, "preview", id],
    queryFn: () => apiRequest<{ url: string }>(api.mediaPreviewUrl(id)),
    enabled,
    retry: false,
    staleTime: 50 * 60_000, // signed URLs last about an hour
  });
}

function KindIcon({ kind, size = 16 }: { kind?: BotMedia["kind"]; size?: number }) {
  if (kind === "video") return <Film size={size} />;
  if (kind === "audio") return <FileAudio size={size} />;
  return <ImageIcon size={size} />;
}

function AudioThumb({ media }: { media: BotMedia }) {
  // Signed URL for the voice note, so the owner can listen before publishing.
  const preview = usePreview(media.id, true);
  const audio = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);

  // A new signed URL means a different clip: reset the player.
  useEffect(() => {
    setPlaying(false);
    audio.current?.pause();
  }, [preview.data?.url]);

  const toggle = () => {
    const el = audio.current;
    if (!el) return;
    if (el.paused) void el.play();
    else el.pause();
  };

  return (
    <span className="grid place-items-center gap-1 px-2 text-center text-muted">
      <button
        aria-label={playing ? "Pausar áudio" : "Ouvir áudio"}
        className="grid size-9 place-items-center rounded-full bg-fg-2/15 text-fg hover:bg-fg-2/25 disabled:opacity-40"
        disabled={!preview.data?.url}
        onClick={toggle}
        title={playing ? "Pausar" : "Ouvir"}
        type="button"
      >
        {playing ? <Pause size={18} /> : <Play size={18} />}
      </button>
      <span className="line-clamp-2 break-all text-[10px]">{media.file_name}</span>
      {preview.data?.url && (
        <audio
          onEnded={() => setPlaying(false)}
          onPause={() => setPlaying(false)}
          onPlay={() => setPlaying(true)}
          preload="none"
          ref={audio}
          src={preview.data.url}
        />
      )}
    </span>
  );
}

function Thumb({ media }: { media?: BotMedia }) {
  const preview = usePreview(media?.id ?? "", Boolean(media) && media?.kind !== "audio");
  if (!media) return <span className="text-xs text-danger">Mídia removida</span>;
  if (media.kind === "audio") return <AudioThumb media={media} />;
  if (media.kind === "photo" && preview.data) {
    return <img alt={media.file_name} className="absolute inset-0 size-full object-cover" loading="lazy" src={preview.data.url} />;
  }
  if (media.kind === "video" && preview.data) {
    return <video autoPlay className="absolute inset-0 size-full object-cover" loop muted playsInline preload="metadata" src={`${preview.data.url}#t=0.1`} />;
  }
  return (
    <span className="grid place-items-center gap-1 px-2 text-center text-muted">
      <KindIcon kind={media.kind} size={22} />
      <span className="line-clamp-2 break-all text-[10px]">{media.file_name}</span>
    </span>
  );
}

/**
 * The SharkBot media tiles: up to ``max`` files sent before the message, in
 * order. New files upload straight from the device; old ones can be reused.
 */
export function MediaGrid({
  value,
  onChange,
  max,
  kinds = ["photo", "video", "audio"],
  title = "Mídias",
}: {
  value: string[];
  onChange: (ids: string[]) => void;
  max: number;
  kinds?: BotMedia["kind"][];
  title?: string;
}) {
  const queryClient = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const replaceInput = useRef<HTMLInputElement>(null);
  const [library, setLibrary] = useState(false);
  // When set, picking a file / library item swaps the media at this position instead of adding.
  const [replaceAt, setReplaceAt] = useState<number | null>(null);
  const api = useBotApi();
  const media = useBotMedia();
  const byId = new Map((media.data?.media ?? []).map((item) => [item.id, item]));
  const cacheCreated = (created: BotMedia[]) =>
    queryClient.setQueryData<{ media: BotMedia[] }>([...api.mediaKey], (old) => ({ media: [...created, ...(old?.media ?? [])] }));
  const swapAt = (index: number, id: string) => onChange(value.map((other, i) => (i === index ? id : other)));
  const upload = useMutation({
    mutationFn: async (files: File[]) => {
      const created: BotMedia[] = [];
      for (const original of files) {
        const file = normalizeUpload(original);
        created.push(
          await apiRequest<BotMedia>(api.mediaUploadUrl(file.name), { method: "POST", body: file }),
        );
      }
      return created;
    },
    onSuccess: (created) => {
      cacheCreated(created);
      onChange([...value, ...created.map((item) => item.id)].slice(0, max));
    },
  });
  // "Alterar mídia": upload a new file into one existing slot (order/links/settings kept).
  const replace = useMutation({
    mutationFn: async ({ file }: { file: File; index: number }) => {
      const normalized = normalizeUpload(file);
      return apiRequest<BotMedia>(api.mediaUploadUrl(normalized.name), { method: "POST", body: normalized });
    },
    onSuccess: (created, { index }) => {
      cacheCreated([created]);
      swapAt(index, created.id);
      setReplaceAt(null);
    },
  });
  const move = (index: number, delta: number) => {
    const next = [...value];
    const target = index + delta;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
  };
  const available = (media.data?.media ?? []).filter((item) => kinds.includes(item.kind) && !value.includes(item.id));

  return (
    <div className="grid gap-2">
      <div className="flex items-center justify-between text-sm text-fg-2">
        <span>
          {title} <span className="text-xs text-muted">(até {max})</span>
        </span>
        <span className="text-xs text-muted">
          {value.length}/{max}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
        {value.map((id, index) => {
          const item = byId.get(id);
          return (
            <div className="relative grid aspect-square place-items-center overflow-hidden rounded-xl border border-line bg-black/40" key={id}>
              <Thumb media={item} />
              <span className="absolute left-1.5 top-1.5 grid size-6 place-items-center rounded-md bg-black/60 text-[11px] font-semibold text-white">
                {index + 1}
              </span>
              <span className="absolute bottom-1.5 left-1.5 rounded-md bg-black/60 p-1 text-white">
                <KindIcon kind={item?.kind} size={12} />
              </span>
              <div className="absolute right-1.5 top-1.5 flex gap-1">
                <button
                  aria-label="Alterar mídia"
                  className="grid size-7 place-items-center rounded-md bg-black/60 text-white"
                  disabled={replace.isPending}
                  onClick={() => {
                    setReplaceAt(index);
                    replaceInput.current?.click();
                  }}
                  title="Alterar mídia (troca só o arquivo)"
                  type="button"
                >
                  <RefreshCw size={13} />
                </button>
                <button
                  aria-label="Remover mídia"
                  className="grid size-7 place-items-center rounded-md bg-danger/90 text-white"
                  onClick={() => onChange(value.filter((other) => other !== id))}
                  type="button"
                >
                  <Trash2 size={13} />
                </button>
              </div>
              {value.length > 1 && (
                <div className="absolute bottom-1.5 right-1.5 flex gap-1">
                  <button aria-label="Mover para a esquerda" className="grid size-7 place-items-center rounded-md bg-black/60 text-white disabled:opacity-30" disabled={index === 0} onClick={() => move(index, -1)} type="button">
                    <ChevronLeft size={14} />
                  </button>
                  <button aria-label="Mover para a direita" className="grid size-7 place-items-center rounded-md bg-black/60 text-white disabled:opacity-30" disabled={index === value.length - 1} onClick={() => move(index, 1)} type="button">
                    <ChevronRight size={14} />
                  </button>
                </div>
              )}
            </div>
          );
        })}
        {value.length < max && (
          <div className="grid aspect-square grid-rows-2 overflow-hidden rounded-xl border border-dashed border-line text-xs text-muted">
            <button
              className="flex flex-col items-center justify-center gap-1 hover:bg-well hover:text-fg disabled:opacity-60"
              disabled={upload.isPending}
              onClick={() => input.current?.click()}
              type="button"
            >
              {upload.isPending ? <span>Enviando…</span> : (<><Upload size={16} /> Enviar</>)}
            </button>
            <button
              className="flex flex-col items-center justify-center gap-1 border-t border-dashed border-line hover:bg-well hover:text-fg"
              onClick={() => setLibrary(true)}
              type="button"
            >
              <Library size={16} /> Biblioteca
            </button>
          </div>
        )}
      </div>
      <input
        accept={kinds.map((kind) => ACCEPT[kind]).join(",")}
        className="hidden"
        multiple={max - value.length > 1}
        onChange={(event) => {
          const files = Array.from(event.target.files ?? []).slice(0, max - value.length);
          event.target.value = "";
          if (files.length) upload.mutate(files);
        }}
        ref={input}
        type="file"
      />
      <input
        accept={kinds.map((kind) => ACCEPT[kind]).join(",")}
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (file && replaceAt !== null) replace.mutate({ file, index: replaceAt });
          else setReplaceAt(null);
        }}
        ref={replaceInput}
        type="file"
      />
      {(() => {
        const err = upload.error ?? replace.error;
        return err ? (
          <p className="text-xs text-danger" role="alert">
            {err instanceof ApiError ? err.message : "Falha no envio do arquivo."}
          </p>
        ) : null;
      })()}
      {replace.isPending && <p className="text-xs text-muted">Trocando a mídia…</p>}
      <Modal open={library} title="Escolher da biblioteca" onClose={() => setLibrary(false)}>
        {available.length === 0 ? (
          <p className="text-sm text-muted">Nenhum arquivo disponível. Use “Enviar” para subir do seu aparelho.</p>
        ) : (
          <div className="grid max-h-[60vh] grid-cols-3 gap-2 overflow-y-auto">
            {available.map((item) => (
              <button
                className="relative grid aspect-square place-items-center overflow-hidden rounded-xl border border-line bg-black/40 hover:border-brand"
                key={item.id}
                onClick={() => {
                  onChange([...value, item.id].slice(0, max));
                  if (value.length + 1 >= max) setLibrary(false);
                }}
                type="button"
              >
                <Thumb media={item} />
                <span className="absolute right-1.5 top-1.5 grid size-6 place-items-center rounded-md bg-brand text-white">
                  <Plus size={13} />
                </span>
              </button>
            ))}
          </div>
        )}
      </Modal>
    </div>
  );
}
