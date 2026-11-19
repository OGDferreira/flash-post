// The welcome shown on the loading screen needs the user's name before the
// session query resolves, so we stash it on login and read it back on reload.
const WELCOME_NAME_KEY = "flashpost:welcome-name";

export function rememberWelcomeName(name: string | null | undefined): void {
  try {
    const trimmed = name?.trim();
    if (trimmed) localStorage.setItem(WELCOME_NAME_KEY, trimmed);
    else localStorage.removeItem(WELCOME_NAME_KEY);
  } catch {
    // Private mode / storage blocked: the welcome just falls back to a generic one.
  }
}

export function forgetWelcomeName(): void {
  try {
    localStorage.removeItem(WELCOME_NAME_KEY);
  } catch {
    // ignore
  }
}

export function welcomeLabel(): string {
  let name: string | null = null;
  try {
    name = localStorage.getItem(WELCOME_NAME_KEY);
  } catch {
    name = null;
  }
  return name ? `Bem-vindo de volta, ${name}` : "Bem-vindo de volta";
}
