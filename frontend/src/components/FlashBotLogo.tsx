import { forwardRef, useId, useSyncExternalStore, type SVGProps } from "react";

import { getFlashBotLogo, subscribeAppearance } from "@/lib/appearance";

/** The FlashBot "F" whose stem ends in a lightning bolt (same path as the brand files). */
const MARK = "M24 9H51L48 17H32.4L30.8 23H45.5L42.6 31H31.5L16 57L21.5 37H15.5Z";

/** FlashBot app icon: rounded blue gradient square with the white bolt-F. FlashPost keeps its own BrandLogo. */
export function FlashBotLogo({ className = "size-9" }: { className?: string }) {
  const id = `fb-logo-${useId().replace(/:/g, "")}`;
  // Profile > Aparência lets each user pick the clean logo or the textured galaxy one.
  const style = useSyncExternalStore(subscribeAppearance, getFlashBotLogo);
  if (style === "galaxy") {
    return <img alt="" aria-hidden="true" className={`${className} rounded-[22%] object-cover`} draggable={false} src="/flashbot-logo-galaxy.png" />;
  }
  return (
    <svg aria-hidden="true" className={className} viewBox="0 0 64 64">
      <defs>
        <linearGradient id={id} x1="0" x2="1" y1="0" y2="1">
          <stop offset="0" stopColor="#5169f4" />
          <stop offset="1" stopColor="#22c1ee" />
        </linearGradient>
      </defs>
      <rect fill={`url(#${id})`} height="64" rx="16" width="64" />
      <path d={MARK} fill="#fff" />
    </svg>
  );
}

type GlyphProps = SVGProps<SVGSVGElement> & { size?: number | string; strokeWidth?: number | string };

/** One-color bolt-F for menus; accepts the same props as a lucide icon so it can sit in the navigation. */
export const FlashBotGlyph = forwardRef<SVGSVGElement, GlyphProps>(function FlashBotGlyph(
  { size = 24, strokeWidth: _strokeWidth, ...props },
  ref,
) {
  return (
    <svg aria-hidden="true" fill="currentColor" height={size} ref={ref} viewBox="8 6 48 54" width={size} {...props}>
      <path d={MARK} />
    </svg>
  );
});
