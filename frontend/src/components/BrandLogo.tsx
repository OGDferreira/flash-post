import { useId } from "react";

/** FlashPost mark (rounded gradient square with an F and a post dot). */
export function BrandLogo({ className = "size-9", animated = false }: { className?: string; animated?: boolean }) {
  const id = `fp-logo-${useId().replace(/:/g, "")}`;
  return (
    <svg aria-hidden="true" className={`${className}${animated ? " logo-anim logo-loop" : ""}`} viewBox="0 0 64 64">
      <defs>
        <linearGradient id={id} x1="0" x2="1" y1="0" y2="1">
          <stop offset="0" stopColor="#5169f4" />
          <stop offset="1" stopColor="#22c1ee" />
        </linearGradient>
      </defs>
      <rect className="l-bg" fill={`url(#${id})`} height="64" rx="16" width="64" />
      <path className="l-f1" d="M14 44V20h24v7H22v4h13v7H22v6z" fill="#fff" />
      <circle className="l-dot" cx="46" cy="22" fill="#fff" opacity=".9" r="5" />
      <path className="l-tail" d="M42 44l8-14v10h-5z" fill="#fff" opacity=".9" />
    </svg>
  );
}
