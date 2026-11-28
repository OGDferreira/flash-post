/** CPF helpers mirrored from the backend (app/core/cpf.py): format + check digits.
 *  Validation here is only a courtesy so the form fails fast; the server validates again. */

export function onlyDigits(value: string): string {
  return value.replace(/\D/g, "");
}

function checkDigit(digits: string, length: number): number {
  let total = 0;
  for (let i = 0; i < length; i += 1) {
    total += Number(digits[i]) * (length + 1 - i);
  }
  const remainder = (total * 10) % 11;
  return remainder === 10 ? 0 : remainder;
}

export function isValidCpf(value: string): boolean {
  const digits = onlyDigits(value);
  if (digits.length !== 11) return false;
  if (digits === digits[0].repeat(11)) return false; // 000... etc. pass the checksum but aren't real
  return checkDigit(digits, 9) === Number(digits[9]) && checkDigit(digits, 10) === Number(digits[10]);
}

/** Progressive mask as the user types: 000.000.000-00. */
export function maskCpf(value: string): string {
  const d = onlyDigits(value).slice(0, 11);
  const parts = [d.slice(0, 3), d.slice(3, 6), d.slice(6, 9)].filter(Boolean);
  let out = parts.join(".");
  if (d.length > 9) out += `-${d.slice(9)}`;
  return out;
}
