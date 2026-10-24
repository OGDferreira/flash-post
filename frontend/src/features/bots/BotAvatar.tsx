import { useState } from "react";

import { FlashBotGlyph } from "@/components/FlashBotLogo";

/** Telegram profile photo of the bot (served by our API, token stays on the server); Flash emblem fallback. */
export function BotAvatar({ botId, name, size = 40 }: { botId?: string | null; name: string; size?: number }) {
  const [failed, setFailed] = useState(false);
  const style = { width: size, height: size };
  if (!botId || failed) {
    return (
      <span
        aria-hidden
        className="grid shrink-0 place-items-center rounded-full border border-line-soft bg-well"
        style={style}
      >
        <FlashBotGlyph size={Math.round(size * 0.78)} />
      </span>
    );
  }
  return (
    <img
      alt={`Foto de ${name}`}
      className="shrink-0 rounded-full border border-line-soft object-cover"
      decoding="async"
      loading="lazy"
      onError={() => setFailed(true)}
      src={`/api/bots/${botId}/photo`}
      style={style}
    />
  );
}
