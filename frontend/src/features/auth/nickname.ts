export function normalizePublicNickname(value: string): string {
  return value.normalize("NFC").trim().replace(/\s+/gu, " ");
}

export function isValidPublicNickname(value: string): boolean {
  const normalized = normalizePublicNickname(value);
  const length = Array.from(normalized).length;
  return length >= 2 && length <= 40 && !/[\p{Cc}\p{Cs}]/u.test(normalized);
}
