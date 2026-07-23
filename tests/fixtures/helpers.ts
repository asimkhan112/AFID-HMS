import { type Page, type APIRequestContext } from '@playwright/test';

export const API = 'http://localhost:8000';

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