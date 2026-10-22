import { forwardRef, type ImgHTMLAttributes } from "react";

import { BrandLogo } from "@/components/BrandLogo";
import { APPS } from "@/lib/brand";

/** Falcon Bot emblem (purple falcon). */
export function FlashBotLogo({ className = "size-9", animated = false }: { className?: string; animated?: boolean }) {
  return <BrandLogo animated={animated} app="bot" className={className} />;
}

type GlyphProps = Omit<ImgHTMLAttributes<HTMLImageElement>, "src"> & { size?: number | string; strokeWidth?: number | string };

/** Falcon Bot emblem sized like a lucide icon, so it can sit in menus and avatars. */
export const FlashBotGlyph = forwardRef<HTMLImageElement, GlyphProps>(function FlashBotGlyph(
  { size = 24, strokeWidth: _strokeWidth, className = "", ...props },
  ref,
) {
  return (
    <img
      alt=""
      aria-hidden="true"
      className={`object-contain ${className}`}
      draggable={false}
      height={size}
      ref={ref}
      src={APPS.bot.emblem}
      width={size}
      {...props}
    />
  );
});
