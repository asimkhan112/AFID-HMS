import { test, expect } from '@playwright/test';
import { loginAs, authHeaders, uniqueId } from '../fixtures/helpers';

const API = 'http://localhost:8000';

// Grounded in a fresh read of routers/auth.py's logout() against the CURRENT
// checkout. Two things changed since the old scaffold:
//
//   1. The response body is no longer just {message: "Logout successful"} --
//      it now also returns `export_status`, one of:
//        "no_queue"        -- current_user.role != doctor, the export branch
//                              never runs at all (its initial value)
//        "empty_queue"     -- doctor, but zero WAITING/ACTIVE patients
//        "exported:<N>"    -- doctor, N patients written to the .xlsx file
//        "error:<message>" -- doctor, but generate_queue_excel() itself threw
//      This actually fixes the old scaffold's core finding ("nothing
//      distinguishes export happened from any other outcome") -- a caller
//      that reads export_status can genuinely tell now.
//
//   2. hod.html's own logout() override (still present, still shows its own
//      confirm() dialog that no other portal shows) now DOES call
//      `api.post('/auth/logout')` before clearing storage -- the old
//      "HOD logout never reaches the backend at all" gap is fixed. The
//      confirm-dialog UX inconsistency itself remains unchanged.

async function seedPatientForDoctor(
  page: import('@playwright/test').Page,
  request: import('@playwright/test').APIRequestContext,
  status?: 'ACTIVE' | 'COMPLETED'
) {
  const headers = await authHeaders(page);
  const res = await request.post(`${API}/patients/`, {
    headers,
    data: {
      mr_number: uniqueId('QA-MR'),
      file_number: uniqueId('QA-F'),
      full_name: 'QA Logout-Export Patient',
      cnic: '77777-7777777-7',
      room: 'Room 12',
      assigned_doctor: 'Dr. Asadullah Khan',
      procedure_category: 'Consultation',
    },
  });
  const patient = await res.json();

  if (status) {
    await request.patch(`${API}/patients/${patient.id}/status`, { headers, data: { status: 'ACTIVE' } });
    if (status === 'COMPLETED') {
      await request.patch(`${API}/patients/${patient.id}/status`, { headers, data: { status: 'COMPLETED' } });
    }
  }

  return patient;
}

test('a doctor with a WAITING/ACTIVE patient in their queue gets export_status "exported:<N>" from /auth/logout, proving the export genuinely ran', async ({ page, request }) => {
  await loginAs(page, 'doctor');
  await seedPatientForDoctor(page, request, 'ACTIVE');
  const headers = await authHeaders(page);

  const res = await request.post(`${API}/auth/logout`, { headers });
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body.message).toBe('Logout successful');
  expect(body.export_status).toMatch(/^exported:\d+$/);
  expect(Number(body.export_status.split(':')[1])).toBeGreaterThan(0);
});

test('a doctor with zero WAITING/ACTIVE patients (only a COMPLETED one on file) gets export_status "empty_queue"', async ({ page, request }) => {
  await loginAs(page, 'doctor');
  await seedPatientForDoctor(page, request, 'COMPLETED');
  const headers = await authHeaders(page);

  const res = await request.post(`${API}/auth/logout`, { headers });
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body.message).toBe('Logout successful');
  expect(body.export_status).toBe('empty_queue');
});

test('non-doctor roles hitting /auth/logout skip the export branch entirely and get export_status "no_queue"', async ({ page, request }) => {
  for (const role of ['receptionist', 'hod'] as const) {
    await loginAs(page, role);
    const headers = await authHeaders(page);
    const res = await request.post(`${API}/auth/logout`, { headers });
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.message).toBe('Logout successful');
    expect(body.export_status).toBe('no_queue');
  }
});

test('doctor portal: clicking "Logout Session" really does call POST /auth/logout, then always clears the session and redirects to Login.html', async ({ page, request }) => {
  await loginAs(page, 'doctor');
  await seedPatientForDoctor(page, request, 'ACTIVE');

  let logoutRequestSeen = false;
  page.on('request', (req) => {
    if (req.method() === 'POST' && req.url().endsWith('/auth/logout')) logoutRequestSeen = true;
  });

  await page.click('button:has-text("Logout Session")');
  await page.waitForURL(/Login\.html$/);

  expect(logoutRequestSeen).toBe(true);
  expect(await page.evaluate(() => localStorage.getItem('afid_token'))).toBeNull();
  expect(await page.evaluate(() => localStorage.getItem('afid_user'))).toBeNull();
});

test('HOD portal: "Logout Portal" now really does call the backend /auth/logout endpoint -- the old "never reaches the backend" gap is fixed, though the confirm() dialog it alone shows is still an inconsistency versus the other two portals', async ({ page }) => {
  await loginAs(page, 'hod');

  let logoutRequestSeen = false;
  page.on('request', (req) => {
    if (req.method() === 'POST' && req.url().endsWith('/auth/logout')) logoutRequestSeen = true;
  });
  page.on('dialog', (dialog) => dialog.accept());

  await page.click('button:has-text("Logout Portal")');
  await page.waitForURL(/Login\.html$/);

  expect(logoutRequestSeen).toBe(true);
  expect(await page.evaluate(() => localStorage.getItem('afid_token'))).toBeNull();
});
