/** LGPD cookie consent (opt-in).
 *
 * Essential cookies (session, CSRF, security) are always allowed — they are
 * strictly necessary to run the service and do not need consent under the LGPD.
 * Anything non-essential (analytics, functional preferences stored for
 * convenience) stays OFF until the person explicitly accepts. The record of the
 * decision is kept per browser so the banner is not shown again.
 */

const STORAGE_KEY = "flash-cookie-consent";
/** Bump when the cookie policy changes materially, so consent is asked again. */
export const CONSENT_VERSION = 1;

export type ConsentDecision = "all" | "essential";

export type ConsentRecord = {
  version: number;
  decision: ConsentDecision;
  at: string; // ISO timestamp
};

export const CONSENT_EVENT = "flash:cookie-consent";

export function readConsent(): ConsentRecord | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as ConsentRecord;
    if (!parsed || typeof parsed.decision !== "string") return null;
    if (parsed.version !== CONSENT_VERSION) return null; // policy changed: ask again
    return parsed;
  } catch {
    return null;
  }
}

/** True only when the person has made a choice for the current policy version. */
export function hasDecided(): boolean {
  return readConsent() !== null;
}

/** True when non-essential categories (analytics/functional) may run. */
export function analyticsAllowed(): boolean {
  return readConsent()?.decision === "all";
}

export function saveConsent(decision: ConsentDecision): void {
  const record: ConsentRecord = {
    version: CONSENT_VERSION,
    decision,
    at: new Date().toISOString(),
  };
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(record));
  } catch {
    /* storage unavailable — the choice still applies for this page load */
  }
  try {
    window.dispatchEvent(new CustomEvent<ConsentRecord>(CONSENT_EVENT, { detail: record }));
  } catch {
    /* CustomEvent unavailable */
  }
}

/** Let the person reopen the banner to change their choice (e.g. from a link). */
export function resetConsent(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
  try {
    window.dispatchEvent(new CustomEvent(CONSENT_EVENT, { detail: null }));
  } catch {
    /* ignore */
  }
}
