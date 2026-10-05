const saoPauloTimeZone = "America/Sao_Paulo";

export function formatAccountConnectedAt(value: string | null): string {
  if (!value) return "Data de conexão indisponível";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Data de conexão indisponível";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: saoPauloTimeZone,
  }).format(date);
}

export function formatConnectedDuration(
  connectedAt: string | null,
  errorAt: string | null,
): string {
  if (!connectedAt || !errorAt) return "Duração indisponível";
  const start = Date.parse(connectedAt);
  const end = Date.parse(errorAt);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) {
    return "Duração indisponível";
  }

  const totalHours = Math.floor((end - start) / 3_600_000);
  if (totalHours === 0) return "menos de 1 hora";
  const days = Math.floor(totalHours / 24);
  const hours = totalHours % 24;
  if (days === 0) return `${totalHours} ${totalHours === 1 ? "hora" : "horas"}`;
  if (hours === 0) return `${days} ${days === 1 ? "dia" : "dias"}`;
  return `${days} ${days === 1 ? "dia" : "dias"} e ${hours} ${
    hours === 1 ? "hora" : "horas"
  }`;
}
