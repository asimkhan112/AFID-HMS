import { type Page, type APIRequestContext } from '@playwright/test';

export const API = 'http://localhost:8000';

// ---------------------------------------------------------------------------
// Ported in from the original QA scaffold's tests/fixtures.ts (a separate,
// test.extend-based fixture file that is being retired in favor of this
// plain-helpers module). CREDS and landingPageRegExp are added here as new,
// standalone exports -- nothing above or below this block is changed.
// ---------------------------------------------------------------------------

export type Role = 'hod' | 'doctor' | 'receptionist';

export const CREDS: Record<Role, { email: string; password: string; page: string }> = {
  hod:          { email: 'hod@afid.mil',       password: 'admin1234',  page: 'hod.html' },
  doctor:       { email: 'doctor@afid.mil',    password: 'doctor1234', page: 'doctor (1).html' },
  receptionist: { email: 'reception@afid.mil', password: 'staff1234',  page: 'staff.html' },
};

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// Login.html's portalForRole() redirects the doctor role to the literal
// filename 'doctor (1).html' -- a plain glob string can't safely match a
// filename with a space and parentheses once the browser percent-encodes it,
// so build a RegExp from the encoded, regex-escaped filename instead.
export function landingPageRegExp(fileName: string): RegExp {
  return new RegExp(escapeRegExp(encodeURI(fileName)) + '$');
}

export async function loginAs(page: Page, role: 'receptionist' | 'doctor' | 'hod' | 'admin') {
  await page.goto('/Login.html');
  
  const credentials: Record<string, { email: string; password: string }> = {
    receptionist: { email: 'reception@afid.mil', password: 'staff1234' },
    doctor: { email: 'doctor@afid.mil', password: 'doctor1234' },
    hod: { email: 'hod@afid.mil', password: 'admin1234' },
    admin: { email: 'hod@afid.mil', password: 'admin1234' },
  };

  const creds = credentials[role];
  await page.fill('#login-email', creds.email);
  await page.fill('#login-password', creds.password);
  await page.click('#login-btn');
  
  // Wait for navigation to complete
  await page.waitForURL((url) => !url.pathname.includes('Login.html'), { timeout: 10000 } as any);
}

export async function authHeaders(page: Page) {
  // Get token from localStorage
  const token = await page.evaluate(() => localStorage.getItem('afid_token'));
  return {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json',
  };
}

export function uniqueId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export async function fillPatientForm(page: Page, data: {
  mr: string;
  file: string;
  name: string;
  cnic: string;
  doctor?: string;
}) {
  await page.fill('#p-mr', data.mr);
  await page.fill('#p-file', data.file);
  await page.fill('#p-name', data.name);
  await page.fill('#p-cnic', data.cnic);
  
  if (data.doctor) {
    const doctorSelect = page.locator('#p-doctor');
    await doctorSelect.selectOption({ label: data.doctor });
  }
}

export function rowFor(page: Page, mr: string) {
  return page.locator(`tr:has(td:has-text("${mr}"))`);
}