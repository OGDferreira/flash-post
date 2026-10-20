import { expect, test, type Page } from '@playwright/test';

async function mockApp(page: Page, home: string | null = 'flashbot') {
  const state = { home, tokenRequests: 0, periods: [] as string[] };
  const user = () => ({ id: 'owner', role: 'OWNER', workspace_role: 'OWNER', home_panel: state.home,
    full_name: 'Teste', nickname: 'Teste', email: 'test@example.com', avatar_url: null });
  await page.addInitScript(() => {
    localStorage.setItem('flashpost-install-prompt-dismissed-until', String(Date.now() + 86400000));
  });
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    let data: unknown;
    if (url.pathname === '/api/auth/me' || url.pathname === '/api/profile') data = user();
    else if (url.pathname === '/api/auth/csrf') data = { csrf_token: 'test-csrf' };
    else if (url.pathname === '/api/profile/preferences') { state.home = route.request().postDataJSON().home_panel; data = user(); }
    else if (url.pathname === '/api/widget/token') { state.tokenRequests++; data = { token: 'fpw_test_token' }; }
    else if (url.pathname === '/api/notifications/goals/me') data = { timezone: 'America/Sao_Paulo', configured: false };
    else if (url.pathname === '/api/bots/stats') {
      const period = url.searchParams.get('period')!;
      state.periods.push(period);
      const total = { leads: 20, sales: 1, buyers: 1, revenue: 20, conversion: 50, ticket: 20, pix_generated: 2, pix_paid: 1 };
      data = { period_label: period === '30d' ? '21/09/2026 a 20/10/2026' : '20/10/2026', time_zone: 'America/Sao_Paulo',
        totals: total, series: Array.from({ length: period === '30d' ? 30 : 1 }, (_, i) => ({ ...total,
          date: new Date(Date.UTC(2026, 9, 20 - i)).toISOString().slice(0, 10) })).reverse(), flows: {}, bots: {} };
    } else if (url.pathname === '/api/affiliates') data = { rows: [] };
    else if (url.pathname === '/api/bots/activity') data = { items: [] };
    else if (url.pathname === '/api/bots/partners-ranking') data = { members: [] };
    else if (url.pathname === '/api/analytics/summary') data = { missing_permissions: [], disconnected_today_accounts: [] };
    else if (url.pathname === '/api/wallet/goals' || url.pathname === '/api/wallet/summary') data = { available: false };
    else return route.fulfill({ status: 503, json: { detail: 'Unrelated API disabled in this test' } });
    await route.fulfill({ json: data });
  });
  return state;
}

for (const mobile of [false, true]) {
  test(`initial choice persists and settings can change it (${mobile ? 'mobile/PWA' : 'desktop'})`, async ({ page }) => {
    if (mobile) {
      await page.setViewportSize({ width: 390, height: 844 });
      await page.addInitScript(() => Object.defineProperty(navigator, 'standalone', { value: true }));
    }
    const state = await mockApp(page, null);
    await page.goto('/configuracoes');
    const dialog = page.getByRole('dialog', { name: 'Onde você quer começar?' });
    await expect(dialog).toBeVisible();
    await dialog.getByRole('button', { name: 'FlashBot', exact: true }).click();
    await expect(page).toHaveURL(/\/feature\/bots$/);
    expect(state.home).toBe('flashbot');
    await page.goto('/');
    await expect(page).toHaveURL(/\/feature\/bots$/);
    await expect(dialog).toHaveCount(0);
    await page.goto('/configuracoes');
    await page.getByRole('button', { name: 'FlashPost', exact: true }).click();
    await expect(page.getByRole('status').filter({ hasText: 'Tela inicial salva.' })).toBeVisible();
    expect(state.home).toBe('flashpost');
    await page.goto('/');
    await expect(page).toHaveURL(/\/dashboard$/);
  });
}

test('today on each entry, PIX conversion and independent thirty-day chart', async ({ page }) => {
  const state = await mockApp(page);
  await page.goto('/feature/bots');
  await expect(page.getByRole('button', { name: 'Hoje', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByText('1 PIX pagos / 2 PIX gerados', { exact: true })).toBeVisible();
  await expect(page.getByText('50%', { exact: true })).toBeVisible();
  await expect(page.getByText('Últimos 30 dias · 21/09/2026 a 20/10/2026')).toBeVisible();
  await page.getByRole('button', { name: '7 dias', exact: true }).click();
  await expect.poll(() => state.periods.includes('7d')).toBe(true);
  await expect(page.getByText('Últimos 30 dias · 21/09/2026 a 20/10/2026')).toBeVisible();
  await page.getByRole('link', { name: 'Configurações', exact: true }).click();
  await page.goBack();
  await expect(page.getByRole('button', { name: 'Hoje', exact: true })).toHaveAttribute('aria-pressed', 'true');
});

test('clipboard receives full script and permission failure allows retry without new token', async ({ page }) => {
  const state = await mockApp(page);
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: {
      write: async () => { throw new Error('Permission denied'); },
      writeText: async (value: string) => { (window as unknown as { copiedScript: string }).copiedScript = value; },
    } });
  });
  await page.goto('/configuracoes');
  await page.getByRole('button', { name: 'Copiar script', exact: true }).click();
  const script = page.getByRole('textbox', { name: 'Script completo do widget' });
  await expect(script).toBeVisible();
  expect(await script.inputValue()).toContain('fpw_test_token');
  expect(state.tokenRequests).toBe(1);
  await page.getByRole('button', { name: 'Copiar script', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Script completo copiado.' })).toBeVisible();
  const copied = await page.evaluate(() => (window as unknown as { copiedScript: string }).copiedScript);
  expect(copied).toEqual(await script.inputValue());
  expect(copied).toContain('/api/widget/today');
  expect(copied).toContain('Script.complete()');
  expect(state.tokenRequests).toBe(1);
});
