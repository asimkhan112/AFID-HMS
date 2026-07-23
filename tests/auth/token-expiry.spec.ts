import crypto from 'crypto';
import { test, expect } from '@playwright/test';
import { loginAs } from '../fixtures/helpers';

const API = 'http://localhost:8000';

// Grounded in AFID backend/auth.py and config.py, plus a fresh read of
// AFID backend/.env against the CURRENT checkout. Unlike the old scaffold's
// checkout (which had no .env at all, only .env.example), this project DOES
// have a real .env file -- but it only overrides DATABASE_URL and
// SECRET_KEY, not ACCESS_TOKEN_EXPIRE_MINUTES/ALGORITHM, and critically it
// means the SECRET_KEY is NOT the class default anymore:
//
//   SECRET_KEY=9f875bce6a5a0aa4de34b275e099d4188c3e0bf6b2ed7f09680cfe1adaac75b5
//   ACCESS_TOKEN_EXPIRE_MINUTES: int = 480   (still the class default)
//   ALGORITHM: str = "HS256"                 (still the class default)
//
// so the forged tokens below are signed with the REAL secret from .env, not
// the old scaffold's literal default string -- using the old default here
// would make every request below fail signature verification for the wrong
// reason (a mismatched key) rather than proving the specific rejection
// branch each test targets.
//
// What HAS changed since the old scaffold: a fresh read of api.js shows
// apiRequest() now DOES special-case a 401 -- it clears afid_token/afid_user
// and calls window.location.replace("Login.html") before throwing. So a bad
// token mid-shift no longer degrades a portal silently; it now bounces the
// user back to the login screen the moment the first API call fails. The
// two UI tests at the bottom are rewritten to prove that redirect actually
// fires, replacing the old scaffold's "silent degradation" findings, which
// no longer hold.

const SECRET_KEY = '9f875bce6a5a0aa4de34b275e099d4188c3e0bf6b2ed7f09680cfe1adaac75b5';

function base64url(input: string): string {
  return Buffer.from(input)
    .toString('base64')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

function forgeToken(payload: Record<string, unknown>): string {
  const header = { alg: 'HS256', typ: 'JWT' };
  const signingInput = `${base64url(JSON.stringify(header))}.${base64url(JSON.stringify(payload))}`;
  const signature = crypto
    .createHmac('sha256', SECRET_KEY)
    .update(signingInput)
    .digest('base64')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
  return `${signingInput}.${signature}`;
}

test('a garbage, non-JWT bearer token is rejected with 401 "Token invalid or expired"', async ({ request }) => {
  const res = await request.get(`${API}/auth/me`, { headers: { Authorization: 'Bearer not-a-real-token-at-all' } });
  expect(res.status()).toBe(401);
  expect((await res.json()).detail).toBe('Token invalid or expired');
});

test('a correctly-signed token whose exp claim is in the past is rejected with 401 -- expiry is genuinely enforced, not just token format', async ({ request }) => {
  const now = Math.floor(Date.now() / 1000);
  const expiredToken = forgeToken({ sub: '1', role: 'doctor', exp: now - 3600 });
  const res = await request.get(`${API}/auth/me`, { headers: { Authorization: `Bearer ${expiredToken}` } });
  expect(res.status()).toBe(401);
  expect((await res.json()).detail).toBe('Token invalid or expired');
});

test('a valid, non-expired token with no "sub" claim is rejected with a distinct 401 -- "Invalid token payload"', async ({ request }) => {
  const now = Math.floor(Date.now() / 1000);
  const noSubToken = forgeToken({ role: 'doctor', exp: now + 3600 });
  const res = await request.get(`${API}/auth/me`, { headers: { Authorization: `Bearer ${noSubToken}` } });
  expect(res.status()).toBe(401);
  expect((await res.json()).detail).toBe('Invalid token payload');
});

test('a valid, non-expired token whose "sub" points to a user id that doesn\'t exist is rejected with a third distinct 401 -- "User not found or inactive"', async ({ request }) => {
  const now = Math.floor(Date.now() / 1000);
  const ghostUserToken = forgeToken({ sub: '999999999', role: 'doctor', exp: now + 3600 });
  const res = await request.get(`${API}/auth/me`, { headers: { Authorization: `Bearer ${ghostUserToken}` } });
  expect(res.status()).toBe(401);
  expect((await res.json()).detail).toBe('User not found or inactive');
});

test('no Authorization header at all is rejected with 401 by FastAPI\'s own OAuth2PasswordBearer, before any of this app\'s own code runs', async ({ request }) => {
  const res = await request.get(`${API}/auth/me`);
  expect(res.status()).toBe(401);
  expect((await res.json()).detail).toBe('Not authenticated');
});

test('doctor portal: once the stored token goes bad, a page reload now redirects to Login.html and clears the session -- the old silent-degradation gap is fixed', async ({ page }) => {
  await loginAs(page, 'doctor');

  await page.evaluate(() => localStorage.setItem('afid_token', 'now-a-garbage-token'));

  let dialogSeen = false;
  page.on('dialog', (dialog) => { dialogSeen = true; dialog.accept(); });

  await page.reload();
  await page.waitForURL(/Login\.html/);

  expect(dialogSeen).toBe(false); // no browser confirm/alert involved in the redirect
  expect(await page.evaluate(() => localStorage.getItem('afid_token'))).toBeNull();
  expect(await page.evaluate(() => localStorage.getItem('afid_user'))).toBeNull();
});

test('HOD portal: the same bad-token reload now redirects to Login.html instead of quietly zeroing out the KPI cards', async ({ page }) => {
  await loginAs(page, 'hod');

  await page.evaluate(() => localStorage.setItem('afid_token', 'now-a-garbage-token'));

  await page.reload();
  await page.waitForURL(/Login\.html/);

  expect(await page.evaluate(() => localStorage.getItem('afid_token'))).toBeNull();
});
