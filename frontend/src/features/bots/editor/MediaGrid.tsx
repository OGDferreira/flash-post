import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, FileAudio, Film, Image as ImageIcon, Library, Plus, Trash2, Upload } from "lucide-react";

import { Modal } from "@/components/ui/Modal";
import { ApiError, apiRequest } from "@/services/api";
import type { BotMedia } from "../types";

const ACCEPT: Record<BotMedia["kind"], string> = {
  photo: "image/jpeg,image/png,image/webp",
  video: "video/mp4",
  audio: "audio/ogg,audio/mpeg,audio/mp4",
};

export function useBotMedia() {
  return useQuery({
    queryKey: ["bots", "media"],
    queryFn: () => apiRequest<{ media: BotMedia[] }>("/api/bots/media/list"),
    retry: false,
    staleTime: 60_000,
  });
}

function usePreview(id: string, enabled: boolean) {
  return useQuery({
    queryKey: ["bots", "media", "preview", id],
    queryFn: () => apiRequest<{ url: string }>(`/api/bots/media/${id}/preview`),
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

function Thumb({ media }: { media?: BotMedia }) {
  const preview = usePreview(media?.id ?? "", Boolean(media) && media?.kind !== "audio");
  if (!media) return <span className="text-xs text-danger">Mídia removida</span>;
  if (media.kind === "photo" && preview.data) {
    return <img alt={media.file_name} className="absolute inset-0 size-full object-cover" loading="lazy" src={preview.data.url} />;
  }
  if (media.kind === "video" && preview.data) {
    return <video className="absolute inset-0 size-full object-cover" muted playsInline preload="metadata" src={`${preview.data.url}#t=0.5`} />;
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
  const [library, setLibrary] = useState(false);
  const media = useBotMedia();
  const byId = new Map((media.data?.media ?? []).map((item) => [item.id, item]));
  const upload = useMutation({
    mutationFn: async (files: File[]) => {
      const created: BotMedia[] = [];
      for (const file of files) {
        created.push(
          await apiRequest<BotMedia>(`/api/bots/media?filename=${encodeURIComponent(file.name)}`, { method: "POST", body: file }),
        );
      }
      return created;
    },
    onSuccess: (created) => {
      queryClient.setQueryData<{ media: BotMedia[] }>(["bots", "media"], (old) => ({ media: [...created, ...(old?.media ?? [])] }));
      onChange([...value, ...created.map((item) => item.id)].slice(0, max));
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
      {upload.error && (
        <p className="text-xs text-danger" role="alert">
          {upload.error instanceof ApiError ? upload.error.message : "Falha no envio do arquivo."}
        </p>
      )}
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
