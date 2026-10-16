import { useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileAudio, FileVideo, Image, Upload, X } from "lucide-react";

import { ApiError, apiRequest } from "@/services/api";
import type { BotMedia } from "./types";

const ACCEPT = "image/jpeg,image/png,image/webp,video/mp4,audio/ogg,audio/mpeg,audio/mp4";

export function useBotMedia() {
  return useQuery({
    queryKey: ["bots", "media"],
    queryFn: () => apiRequest<{ media: BotMedia[] }>("/api/bots/media/list"),
    retry: false,
  });
}

function MediaIcon({ kind }: { kind: BotMedia["kind"] }) {
  if (kind === "video") return <FileVideo size={14} />;
  if (kind === "audio") return <FileAudio size={14} />;
  return <Image size={14} />;
}

/** Chooses uploaded media for a block/delivery; uploads new files in place. */
export function MediaPicker({
  value,
  onChange,
  max,
  kinds,
}: {
  value: string[];
  onChange: (ids: string[]) => void;
  max: number;
  kinds?: BotMedia["kind"][];
}) {
  const queryClient = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const media = useBotMedia();
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
      void queryClient.invalidateQueries({ queryKey: ["bots", "media"] });
      const ids = created.map((item) => item.id);
      onChange(max === 1 ? ids.slice(0, 1) : [...value, ...ids].slice(0, max));
    },
  });
  const all = media.data?.media ?? [];
  const byId = new Map(all.map((item) => [item.id, item]));
  const available = all.filter((item) => !value.includes(item.id) && (!kinds || kinds.includes(item.kind)));

  return (
    <div className="grid gap-2">
      {value.length > 0 && (
        <ul className="flex flex-wrap gap-2">
          {value.map((id) => (
            <li className="inline-flex max-w-full items-center gap-1.5 rounded-full bg-brand-soft px-2.5 py-1 text-xs text-accent" key={id}>
              {byId.get(id) && <MediaIcon kind={byId.get(id)!.kind} />}
              <span className="max-w-[180px] truncate">{byId.get(id)?.file_name ?? "mídia removida"}</span>
              <button aria-label="Remover mídia" onClick={() => onChange(value.filter((item) => item !== id))} type="button">
                <X size={13} />
              </button>
            </li>
          ))}
        </ul>
      )}
      {value.length < max && (
        <div className="flex flex-wrap gap-2">
          <select
            className="field min-w-0 flex-1 !text-xs"
            value=""
            onChange={(event) => event.target.value && onChange(max === 1 ? [event.target.value] : [...value, event.target.value])}
          >
            <option value="">{available.length ? "Escolher mídia já enviada…" : "Nenhuma mídia enviada"}</option>
            {available.map((item) => (
              <option key={item.id} value={item.id}>
                {item.file_name}
              </option>
            ))}
          </select>
          <button className="btn-secondary btn-sm" disabled={upload.isPending} onClick={() => input.current?.click()} type="button">
            <Upload size={14} /> {upload.isPending ? "Enviando..." : "Enviar arquivo"}
          </button>
          <input
            accept={ACCEPT}
            className="hidden"
            multiple={max > 1}
            onChange={(event) => {
              const files = Array.from(event.target.files ?? []).slice(0, max - value.length);
              event.target.value = "";
              if (files.length) upload.mutate(files);
            }}
            ref={input}
            type="file"
          />
        </div>
      )}
      {upload.error && (
        <p className="text-xs text-danger">{upload.error instanceof ApiError ? upload.error.message : "Falha no envio."}</p>
      )}
    </div>
  );
}
