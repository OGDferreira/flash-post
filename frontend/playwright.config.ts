import { defineConfig } from "@playwright/test";

// Fluxos de ponta a ponta. Precisam do frontend (5173) e da API rodando, com um usuário dono.
// E2E_BASE_URL / E2E_EMAIL / E2E_PASSWORD sobrescrevem os padrões; E2E_CHROMIUM aponta um Chromium já instalado.
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5173",
    launchOptions: {
      executablePath: process.env.E2E_CHROMIUM || undefined,
      args: ["--headless=new"],
    },
  },
});
