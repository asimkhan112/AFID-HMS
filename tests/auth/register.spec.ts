import { test, expect } from '@playwright/test';
import { CREDS } from '../fixtures/helpers';

const API = 'http://localhost:8000';

// Grounded in a fresh read of routers/auth.py and Login.html against the
// CURRENT checkout: /auth/register now requires
// `current_user: models.User = Depends(get_current_user)` -- i.e. a valid
// Bearer token -- where the old scaffold (and Login.html's own registration
// tab) assumed it was a public, unauthenticated endpoint. Login.html's
// handleRegister() still POSTs /auth/register with no Authorization header
// (there's no session yet on the login page), so every anonymous signup
// attempt now gets a 401 there. api.js's apiRequest() special-cases 401 by
// clearing storage and redirecting to Login.html before throwing "Session
// expired. Please log in again." (see token-expiry.spec.ts for the same
// mechanism) -- NOT the "self-registration is not yet enabled" copy
// handleRegister() shows for a 404, and not the old "pending verification"
// success banner.
//
// Net effect: the public Registration tab on Login.html is now completely
// broken -- a real regression from the old scaffold's checkout, where
// anonymous self-registration worked end-to-end. Because that same 401
// handling also triggers a real page redirect, asserting on the transient
// #reg-error banner text is racy (the redirect can wipe it before Playwright
// observes it), so the first test below proves the regression through
// durable signals instead: no success banner, and no account ever created.

function uniqueEmail(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 1000)}@afid.mil`;
}

async function fillRegisterForm(
  page: import('@playwright/test').Page,
  opts: { firstName: string; lastName: string; email: string; staffId?: string; role: string; password: string }
) {
  await page.fill('#reg-firstname', opts.firstName);
  await page.fill('#reg-lastname', opts.lastName);
  await page.fill('#reg-email', opts.email);
  if (opts.staffId) await page.fill('#reg-staffid', opts.staffId);
  await page.selectOption('#reg-role', opts.role);
  await page.fill('#reg-password', opts.password);
}

async function apiLogin(request: import('@playwright/test').APIRequestContext, role: 'hod' | 'doctor' | 'receptionist') {
  const { email, password } = CREDS[role];
  const res = await request.post(`${API}/auth/login`, { data: { email, password } });
  const { access_token } = await res.json();
  return { Authorization: `Bearer ${access_token}` };
}

test('the public Registration tab on Login.html is broken: submitting it with no session never creates an account or shows the success banner', async ({ page, request }) => {
  const email = uniqueEmail('qa-newuser');
  const password = 'password123';

  await page.goto('/Login.html');
  await page.click('#btn-register');
  await fillRegisterForm(page, {
    firstName: 'QA', lastName: 'NewUser', email, staffId: 'HMS-9001', role: 'receptionist', password,
  });
  await page.click('#reg-btn');
  await page.waitForTimeout(1000);

  await expect(page.locator('#reg-success')).toBeHidden();

  // The durable, non-racy proof: no account for this email was ever created.
  const loginRes = await request.post(`${API}/auth/login`, { data: { email, password } });
  expect(loginRes.status()).toBe(401);
});

test('directly confirms /auth/register now requires authentication -- an anonymous POST (no Authorization header) is rejected with 401, which is the root cause of the UI regression above', async ({ request }) => {
  const email = uniqueEmail('qa-anon-register');
  const res = await request.post(`${API}/auth/register`, {
    data: { full_name: 'QA Anon', email, password: 'password123', role: 'receptionist', staff_id: null },
  });
  expect(res.status()).toBe(401);

  const loginRes = await request.post(`${API}/auth/login`, { data: { email, password: 'password123' } });
  expect(loginRes.status()).toBe(401);
});

test('an authenticated HOD can create a new user via POST /auth/register, and that user can immediately log in', async ({ request }) => {
  // The endpoint itself works correctly for a legitimate, authenticated
  // caller -- the regression above is specifically that Login.html's public
  // tab has no session to attach, not that the backend route is broken.
  const headers = await apiLogin(request, 'hod');
  const email = uniqueEmail('qa-hod-created');
  const password = 'password123';

  const createRes = await request.post(`${API}/auth/register`, {
    headers,
    data: { full_name: 'QA HOD-Created User', email, password, role: 'receptionist', staff_id: null },
  });
  expect(createRes.status()).toBe(201);
  const created = await createRes.json();
  expect(created.email).toBe(email);
  expect(created.is_active).toBe(true);

  const loginRes = await request.post(`${API}/auth/login`, { data: { email, password } });
  expect(loginRes.status()).toBe(200);
  const { access_token } = await loginRes.json();
  expect(access_token).toBeTruthy();
});

test('a receptionist-authenticated caller can create an ordinary (non-admin) account, but is blocked from creating an admin account', async ({ request }) => {
  // register()'s only privilege check is specifically for role == admin
  // ("Only admin/HOD can create admin accounts") -- any other authenticated
  // caller, of any role, can still create a non-admin account. That's a real
  // gap (no receptionist should be able to enroll a new doctor/nurse
  // account on their own authority), documented here as a contrast to the
  // admin-role check that DOES work.
  const headers = await apiLogin(request, 'receptionist');

  const okEmail = uniqueEmail('qa-receptionist-created');
  const okRes = await request.post(`${API}/auth/register`, {
    headers,
    data: { full_name: 'QA Receptionist-Created Nurse', email: okEmail, password: 'password123', role: 'nurse', staff_id: null },
  });
  expect(okRes.status()).toBe(201);

  const adminEmail = uniqueEmail('qa-receptionist-selfadmin');
  const adminRes = await request.post(`${API}/auth/register`, {
    headers,
    data: { full_name: 'QA Receptionist SelfAdmin', email: adminEmail, password: 'password123', role: 'admin', staff_id: null },
  });
  expect(adminRes.status()).toBe(403);
  expect((await adminRes.json()).detail).toBe('Only admin/HOD can create admin accounts');
});

test('registration with a duplicate email is rejected with a 400, even for an authenticated caller', async ({ request }) => {
  const headers = await apiLogin(request, 'hod');
  const email = uniqueEmail('qa-dupe');
  const data = { full_name: 'QA Dupe', email, password: 'password123', role: 'receptionist', staff_id: null };

  const firstRes = await request.post(`${API}/auth/register`, { headers, data });
  expect(firstRes.status()).toBe(201);

  const secondRes = await request.post(`${API}/auth/register`, { headers, data: { ...data, full_name: 'QA Dupe Again' } });
  expect(secondRes.status()).toBe(400);
  expect((await secondRes.json()).detail).toBe('Email already registered');
});

test('registration with a too-short password is still rejected client-side by Login.html\'s own form validation, independent of the auth-gate regression above', async ({ page }) => {
  // #reg-password carries minlength="8" -- the browser blocks the submit
  // event entirely before handleRegister() ever runs, so this one still
  // behaves exactly as before regardless of what /auth/register now
  // requires server-side.
  const email = uniqueEmail('qa-shortpw');
  const shortPassword = 'abc123'; // 6 chars, under minlength="8"

  await page.goto('/Login.html');
  await page.click('#btn-register');
  await fillRegisterForm(page, { firstName: 'QA', lastName: 'ShortPw', email, role: 'receptionist', password: shortPassword });

  const passwordField = page.locator('#reg-password');
  const validity = await passwordField.evaluate((el: HTMLInputElement) => ({
    valid: el.validity.valid,
    tooShort: el.validity.tooShort,
  }));
  expect(validity.valid).toBe(false);
  expect(validity.tooShort).toBe(true);

  await page.click('#reg-btn');

  await expect(page.locator('#reg-success')).toBeHidden();
  await expect(page.locator('#reg-error')).toBeHidden();
});
