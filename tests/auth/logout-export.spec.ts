import { test, expect } from '../fixtures/helpers';
import { DIALOG, acceptDialog } from '../fixtures/helpers';
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

const DOCTOR_NAME = 'Dr. Asadullah Khan';

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
      assigned_doctor: DOCTOR_NAME,
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

/** The real WAITING/ACTIVE queue for DOCTOR_NAME right now. The shared dev
 *  database is NOT guaranteed to be empty for this doctor -- it can carry
 *  real, non-QA baseline patients that no cleanup script or fixture should
 *  ever touch -- so tests must never assume a hardcoded starting count. */
async function realQueueForDoctor(request: import('@playwright/test').APIRequestContext, headers: Record<string, string>) {
  const [waiting, active] = await Promise.all([
    request.get(`${API}/patients/?status=WAITING`, { headers }).then((r) => r.json()),
    request.get(`${API}/patients/?status=ACTIVE`, { headers }).then((r) => r.json()),
  ]);
  return [...waiting, ...active].filter((p: any) => p.assigned_doctor === DOCTOR_NAME);
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

test('a COMPLETED-only patient added does not inflate the queue -- export_status reflects only the real pre-existing WAITING/ACTIVE count, which may not be zero', async ({ page, request }) => {
  await loginAs(page, 'doctor');
  const headers = await authHeaders(page);

  // Ground truth taken BEFORE this test touches anything. This used to
  // hardcode an expectation of exactly "empty_queue", which assumed this
  // doctor's WAITING/ACTIVE queue in the shared dev database starts at
  // genuinely zero. In practice it doesn't: this database carries a small
  // number of real, non-QA baseline patients (not created by any test, so
  // never touched by AFID backend/cleanup_qa_test_data.py or the suite-wide
  // qaPatientCleanup fixture in tests/fixtures/helpers.ts -- both correctly
  // leave real data alone), and some of those are assigned to this doctor.
  // The actual thing this test verifies -- a COMPLETED patient contributes
  // nothing to the export -- still holds regardless of that baseline; it
  // just has to compare against the real count instead of assuming zero.
  const before = await realQueueForDoctor(request, headers);

  await seedPatientForDoctor(page, request, 'COMPLETED');

  const res = await request.post(`${API}/auth/logout`, { headers });
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body.message).toBe('Logout successful');

  if (before.length === 0) {
    expect(body.export_status).toBe('empty_queue');
  } else {
    // The COMPLETED patient we just seeded must NOT be counted -- the queue
    // size should be exactly what it was before, no more.
    expect(body.export_status).toBe(`exported:${before.length}`);
  }
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

test('HOD portal: "Logout Portal" calls the backend /auth/logout endpoint, behind an in-page confirmation rather than a native confirm()', async ({ page }) => {
  await loginAs(page, 'hod');

  let logoutRequestSeen = false;
  page.on('request', (req) => {
    if (req.method() === 'POST' && req.url().endsWith('/auth/logout')) logoutRequestSeen = true;
  });
  let nativeDialogFired = false;
  page.on('dialog', async (dialog) => { nativeDialogFired = true; await dialog.dismiss(); });

  await page.click('button:has-text("Logout Portal")');

  // The HOD portal still asks for confirmation before logging out (it is the
  // only portal that does), but it now uses the same in-page dialog as the
  // rest of the app instead of a native confirm() prefixed by the page origin.
  await expect(page.locator(DIALOG)).toBeVisible({ timeout: 10000 });
  await acceptDialog(page);

  await page.waitForURL(/Login\.html$/);

  expect(logoutRequestSeen).toBe(true);
  expect(nativeDialogFired).toBe(false);
  expect(await page.evaluate(() => localStorage.getItem('afid_token'))).toBeNull();
});
