import { useSyncExternalStore } from "react";

import { APPS, type AppId } from "@/lib/brand";
import { getTheme } from "@/lib/theme";

function subscribeTheme(listener: () => void) {
  window.addEventListener("flashpost:theme", listener);
  return () => window.removeEventListener("flashpost:theme", listener);
}

/** The falcon emblem of a tool (Falcon Post by default). ``animated``: the entry animation
 * (the ring turns in, the falcon lands, a light sweep crosses it), see .falcon-anim in index.css. */
export function BrandLogo({
  className = "size-9",
  animated = false,
  app = "post",
}: {
  className?: string;
  animated?: boolean;
  app?: AppId;
}) {
  return (
    <span aria-hidden="true" className={`falcon-emblem relative inline-block shrink-0 ${className}${animated ? " falcon-anim" : ""}`}>
      <img alt="" className="size-full object-contain" draggable={false} src={APPS[app].emblem} />
      {animated && <span className="falcon-shine" />}
    </span>
  );
}

/** "FALCON POST" / "FALCON BOT" wordmark (with or without the emblem), light or dark following the theme. */
export function BrandLockup({
  app = "post",
  className = "h-8",
  kind = "lockup",
}: {
  app?: AppId;
  className?: string;
  /** lockup = emblem + name; wordmark = name only (when the emblem is already beside it). */
  kind?: "lockup" | "wordmark";
}) {
  const theme = useSyncExternalStore(subscribeTheme, getTheme);
  const name = app === "bot" ? "falconbot" : "falconpost";
  return (
    <img
      alt={APPS[app].name}
      className={`${className} w-auto object-contain`}
      draggable={false}
      src={`/brand/${name}-${kind}-${theme === "light" ? "light" : "dark"}.webp`}
    />
  );
}
