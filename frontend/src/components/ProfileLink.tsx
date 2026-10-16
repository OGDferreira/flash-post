import { ExternalLink } from "lucide-react";

/** "abrir ↗" link to an account's Instagram profile in a new tab. */
export function ProfileLink({ username }: { username: string }) {
  return (
    <a
      aria-label={`Abrir o perfil @${username} no Instagram`}
      className="inline-flex shrink-0 items-center gap-1 text-xs text-accent hover:text-white"
      href={`https://www.instagram.com/${encodeURIComponent(username)}/`}
      onClick={(event) => event.stopPropagation()}
      rel="noreferrer"
      target="_blank"
    >
      abrir <ExternalLink size={11} />
    </a>
  );
}
