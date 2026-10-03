import { useEffect, useState } from "react";
import { Instagram } from "lucide-react";

type InstagramAvatarProps = {
  src: string | null;
  username: string;
  className: string;
};

export function InstagramAvatar({ src, username, className }: InstagramAvatarProps) {
  const [failed, setFailed] = useState(false);

  useEffect(() => setFailed(false), [src]);

  if (src && !failed) {
    return (
      <img
        alt={`Foto de perfil de @${username}`}
        className={className}
        src={src}
        referrerPolicy="no-referrer"
        onError={() => setFailed(true)}
      />
    );
  }

  return (
    <span
      aria-label={`Foto de perfil indisponível para @${username}`}
      className={`grid shrink-0 place-items-center bg-[#171e31] text-[#8295ff] ${className}`}
      role="img"
    >
      <Instagram size={16} />
    </span>
  );
}
