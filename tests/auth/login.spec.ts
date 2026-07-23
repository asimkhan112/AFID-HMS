import { test, expect } from '@playwright/test';
import { CREDS, Role, landingPageRegExp } from '../fixtures/helpers';

const roles: Role[] = ['hod', 'doctor', 'receptionist'];

for (const role of roles) {
  test(`valid login as ${role} redirects to the correct portal and stores the session`, async ({ page }) => {
    const { email, password, page: landingPage } = CREDS[role];

    await page.goto('/Login.html');
    await page.fill('#login-email', email);
    await page.fill('#login-password', password);
    await page.click('#login-btn');

    await page.waitForURL(landingPageRegExp(landingPage));

    const token = await page.evaluate(() => localStorage.getItem('afid_token'));
    const user = await page.evaluate(() => localStorage.getItem('afid_user'));
    expect(token).toBeTruthy();
    expect(user).toBeTruthy();

    // #login-error lives on Login.html, not the portal page we've navigated
    // to -- confirm it simply isn't present here, i.e. nothing carried over.
    await expect(page.locator('#login-error')).toHaveCount(0);
  });
}

test('invalid password shows an error and does not redirect', async ({ page }) => {
  await page.goto('/Login.html');
  await page.fill('#login-email', CREDS.hod.email);
  await page.fill('#login-password', 'definitely-the-wrong-password');
  await page.click('#login-btn');

  const error = page.locator('#login-error');
  await expect(error).toBeVisible();
  await expect(error).not.toBeEmpty();

  expect(page.url()).toContain('Login.html');
  const token = await page.evaluate(() => localStorage.getItem('afid_token'));
  const user = await page.evaluate(() => localStorage.getItem('afid_user'));
  expect(token).toBeNull();
  expect(user).toBeNull();
});

test('login with a non-existent email is rejected, not a silent failure', async ({ page }) => {
  await page.goto('/Login.html');
  await page.fill('#login-email', 'nobody-by-this-name@afid.mil');
  await page.fill('#login-password', 'whatever-password');
  await page.click('#login-btn');

  const error = page.locator('#login-error');
  await expect(error).toBeVisible();
  await expect(error).not.toBeEmpty();

  expect(page.url()).toContain('Login.html');
  const token = await page.evaluate(() => localStorage.getItem('afid_token'));
  const user = await page.evaluate(() => localStorage.getItem('afid_user'));
  expect(token).toBeNull();
  expect(user).toBeNull();

  // Confirm the UI doesn't get stuck mid-request: button re-enabled, spinner hidden.
  await expect(page.locator('#login-btn')).toBeEnabled();
  const spinner = page.locator('#login-spinner');
  if (await spinner.count()) {
    await expect(spinner).toBeHidden();
  }
});
