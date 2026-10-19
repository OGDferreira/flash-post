import { forwardRef, useSyncExternalStore, type SVGProps } from "react";

import { BrandLogo } from "@/components/BrandLogo";
import { GLYPH_DROP_BIG, GLYPH_DROP_SMALL, GLYPH_F, GLYPH_TRANSFORM } from "@/components/brandMark";
import { getFlashBotLogo, subscribeAppearance } from "@/lib/appearance";

/** FlashBot app icon: the same logo as FlashPost (one brand), or the galaxy one if the user picked it. */
export function FlashBotLogo({ className = "size-9" }: { className?: string }) {
  // Configurações > Aparência lets each user pick the standard logo or the textured galaxy one.
  const style = useSyncExternalStore(subscribeAppearance, getFlashBotLogo);
  if (style === "galaxy") {
    return <img alt="" aria-hidden="true" className={`${className} rounded-[22%] object-cover`} draggable={false} src="/flashbot-logo-galaxy.png" />;
  }
  return <BrandLogo className={className} />;
}

type GlyphProps = SVGProps<SVGSVGElement> & { size?: number | string; strokeWidth?: number | string };

/** One-color mark for menus; accepts the same props as a lucide icon so it can sit in the navigation. */
export const FlashBotGlyph = forwardRef<SVGSVGElement, GlyphProps>(function FlashBotGlyph(
  { size = 24, strokeWidth: _strokeWidth, ...props },
  ref,
) {
  return (
    <svg aria-hidden="true" fill="currentColor" height={size} ref={ref} viewBox="12 10 42 47" width={size} {...props}>
      <path d={GLYPH_F} transform={GLYPH_TRANSFORM} />
      <path d={GLYPH_DROP_BIG} transform={GLYPH_TRANSFORM} />
      <path d={GLYPH_DROP_SMALL} transform={GLYPH_TRANSFORM} />
    </svg>
  );
});
