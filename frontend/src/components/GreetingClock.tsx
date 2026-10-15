import { useEffect, useState } from "react";

const TZ = "America/Sao_Paulo";
const dateFormat = new Intl.DateTimeFormat("pt-BR", {
  weekday: "long",
  day: "2-digit",
  month: "long",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: TZ,
});

/** "Boa tarde, Fulano" + date and time (no seconds). Ticks once per 30 s. */
export function GreetingClock({ nickname }: { nickname: string | undefined }) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 30_000);
    return () => window.clearInterval(timer);
  }, []);
  const hour = Number(
    new Intl.DateTimeFormat("en-US", { hour: "numeric", hourCycle: "h23", timeZone: TZ }).format(now),
  );
  const greeting = hour < 12 ? "Bom dia" : hour < 18 ? "Boa tarde" : "Boa noite";
  return (
    <div className="min-w-0">
      <h2 className="truncate text-xl font-semibold tracking-[-0.02em] text-fg sm:text-2xl">
        {greeting}, {nickname ?? "bem-vindo"}
      </h2>
      <p className="mt-0.5 text-sm text-muted first-letter:uppercase">
        <time dateTime={now.toISOString()}>{dateFormat.format(now)}</time>
      </p>
    </div>
  );
}
