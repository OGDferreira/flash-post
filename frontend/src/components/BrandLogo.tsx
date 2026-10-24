import { APPS, type AppId } from "@/lib/brand";

/** The Flash emblem (the lightning bolt). ``animated``: the entry animation
 * (the ring turns in, the mark lands, a light sweep crosses it), see .falcon-anim in index.css. */
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

/** "Flash" wordmark, optionally with the emblem. Rendered as text in the brand font so it
 * follows the theme (currentColor) and needs no per-name image. */
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
  return (
    <span className={`inline-flex items-center gap-2 text-fg ${className}`}>
      {kind === "lockup" && (
        <img alt="" className="h-full w-auto object-contain" draggable={false} src={APPS[app].emblem} />
      )}
      <svg className="h-full w-auto" viewBox="0 0 150 48" role="img" aria-label={APPS[app].name} fill="currentColor">
        <text
          x="0"
          y="37"
          fontFamily="'Space Grotesk Variable','Space Grotesk',system-ui,sans-serif"
          fontSize="40"
          fontWeight="700"
          letterSpacing="-1.5"
        >
          Flash
        </text>
      </svg>
    </span>
  );
}
