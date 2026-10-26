import { expect, test } from '@playwright/test'

test('login page renders the unauthenticated credentials form', async ({ page }) => {
  await page.route('**/api/auth/me', (route) =>
    route.fulfill({
      status: 401,
      contentType: 'application/json',
      body: JSON.stringify({ detail: '未登录' }),
    }),
  )

  await page.goto('/login')

  await expect(page.getByRole('heading', { name: 'LexRAG' })).toBeVisible()
  await expect(page.getByRole('textbox', { name: '用户名' })).toBeVisible()
  await expect(page.getByRole('textbox', { name: '密码' })).toBeVisible()
  await expect(page.getByRole('button', { name: /登\s*录|login/i })).toBeVisible()
})
