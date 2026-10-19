import { useId } from "react";

import { BRAND_GRADIENT, GLYPH_DROP_BIG, GLYPH_DROP_SMALL, GLYPH_F, GLYPH_TRANSFORM } from "@/components/brandMark";

/** FlashPost and FlashBot share this logo. ``animated``: the F flies in, the speed drops trail
 * behind it, a shine crosses the tile, then a slow pulse (see .logo-anim in index.css). */
export function BrandLogo({ className = "size-9", animated = false }: { className?: string; animated?: boolean }) {
  const id = `fp-logo-${useId().replace(/:/g, "")}`;
  return (
    <svg aria-hidden="true" className={`${className}${animated ? " logo-anim logo-loop" : ""}`} viewBox="0 0 64 64">
      <defs>
        <linearGradient id={`${id}-g`} x1="0" x2="1" y1="0" y2="1">
          <stop offset="0" stopColor={BRAND_GRADIENT[0]} />
          <stop offset=".5" stopColor={BRAND_GRADIENT[1]} />
          <stop offset="1" stopColor={BRAND_GRADIENT[2]} />
        </linearGradient>
        {animated && (
          <>
            <linearGradient id={`${id}-s`} x1="0" x2="1" y1="0" y2="0">
              <stop offset="0" stopColor="#fff" stopOpacity="0" />
              <stop offset=".5" stopColor="#fff" stopOpacity=".55" />
              <stop offset="1" stopColor="#fff" stopOpacity="0" />
            </linearGradient>
            <clipPath id={`${id}-c`}>
              <rect height="64" rx="15" width="64" />
            </clipPath>
          </>
        )}
      </defs>
      <rect className="l-bg" fill={`url(#${id}-g)`} height="64" rx="15" width="64" />
      <g className="l-d2">
        <path d={GLYPH_DROP_SMALL} fill="#fff" transform={GLYPH_TRANSFORM} />
      </g>
      <g className="l-d1">
        <path d={GLYPH_DROP_BIG} fill="#fff" transform={GLYPH_TRANSFORM} />
      </g>
      <g className="l-f">
        <path d={GLYPH_F} fill="#fff" transform={GLYPH_TRANSFORM} />
      </g>
      {animated && (
        <g clipPath={`url(#${id}-c)`}>
          <rect className="l-shine" fill={`url(#${id}-s)`} height="96" width="18" x="-30" y="-16" />
        </g>
      )}
    </svg>
  );
}
