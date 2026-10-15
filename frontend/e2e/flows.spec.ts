import { expect, test, type Page } from "@playwright/test";

const email = process.env.E2E_EMAIL ?? "demo@flashpost.dev";
const password = process.env.E2E_PASSWORD ?? "demo12345";

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Senha", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard/);
}

test("rota protegida sem sessão leva ao login", async ({ page }) => {
  await page.goto("/feature/accounts");
  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByRole("heading", { name: "Entrar" })).toBeVisible();
});

test("login mostra a copy financeira e rejeita senha errada", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByText("dinheiro no bolso.")).toBeVisible();
  // e-mail inexistente: não aciona o bloqueio por tentativas do usuário real
  await page.getByLabel("E-mail").fill("nao-existe@flashpost.dev");
  await page.getByLabel("Senha", { exact: true }).fill("senha-errada-123");
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page).toHaveURL(/\/login/);
});

test("cadastro abre com o mesmo layout", async ({ page }) => {
  await page.goto("/register");
  await expect(page.getByText("receita previsível.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Criar conta" })).toBeVisible();
});

test("entrar, abrir Contatos e sair volta ao login", async ({ page }) => {
  await login(page);
  await page.goto("/feature/contacts");
  await expect(page.getByText("+55 27 99938-4259")).toBeVisible();
  await page.getByRole("button", { name: /^Sair/ }).first().click();
  await expect(page).toHaveURL(/\/login/);
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login/);
});
