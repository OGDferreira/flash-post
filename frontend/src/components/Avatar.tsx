import { useState } from "react";

/** Round user photo with an initial fallback (also used when the image fails). */
export function Avatar({
  name,
  src,
  className = "size-8",
}: {
  name: string;
  src?: string | null;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);
  if (src && !failed) {
    return (
      <img
        alt=""
        className={`${className} shrink-0 rounded-full border border-line object-cover`}
        loading="lazy"
        onError={() => setFailed(true)}
        src={src}
      />
    );
  }
  return (
    <span
      aria-hidden="true"
      className={`${className} grid shrink-0 place-items-center rounded-full bg-brand-soft text-xs font-semibold text-accent`}
    >
      {(name.trim().slice(0, 1) || "?").toUpperCase()}
    </span>
  );
}
