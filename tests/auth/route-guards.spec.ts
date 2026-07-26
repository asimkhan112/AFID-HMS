import { test, expect } from '../fixtures/helpers';
import { futureLeaveWindow, clearOwnPendingLeaves } from '../fixtures/helpers';
import { loginAs, CREDS } from '../fixtures/helpers';

const API = 'http://localhost:8000';

function uniqueId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
}

async function apiLogin(request: import('@playwright/test').APIRequestContext, role: 'hod' | 'doctor' | 'receptionist') {
  const { email, password } = CREDS[role];
  const res = await request.post(`${API}/auth/login`, { data: { email, password } });
  const { access_token } = await res.json();
  return { Authorization: `Bearer ${access_token}` };
}

// Grounded in a fresh read of routers/hod.py and routers/staff.py against
// the CURRENT checkout: every endpoint on both routers sits behind
// `Depends(require_role(models.UserRole.hod, models.UserRole.admin))`,
// with two narrow read-only carve-outs on GET /hod/timeline/{mr}: `doctor`
// (a doctor needs to check their own patients' timelines) and
// `receptionist` (staff.html's reception portal has its own Patient
// Timeline page that reads from this exact endpoint -- see
// tests/timeline/patient-timeline.spec.ts. Blocking receptionist here used
// to silently break that page, since the frontend's try/catch swallowed
// every 403 into an empty timeline, indistinguishable from a patient with
// genuinely no steps). The POST/PATCH timeline-step endpoints stay
// hod/admin/doctor-only -- receptionists can view timelines but not create
// or edit steps. The old scaffold found all of this completely unguarded --
// any authenticated role could read and write HOD/staff data. That gap is
// fixed here: a receptionist or doctor token now gets a real 403 from
// everything else, matching the leave-approval endpoint's existing (and
// still-correct) role check, which used to be the lone exception and is
// now the model the rest of the app follows.
//
// The frontend still has no on-load guard of its own (grep of hod.html /
// staff.html / doctor (1).html confirms this hasn't changed) -- the portal
// HTML/JS still happily loads for any role. It's just that every API call
// the page makes now fails quietly, leaving the dashboard showing its
// zeroed initial state instead of real data, rather than genuinely leaking
// it as before.

test('UI: a receptionist can still navigate straight to hod.html, but the page never shows real HOD KPI data now that every backing API call is correctly rejected', async ({ page }) => {
  await loginAs(page, 'receptionist');

  await page.goto('/hod.html');
  await page.waitForLoadState('networkidle');

  // No frontend guard bounces the receptionist away -- same gap as before.
  await expect(page).toHaveURL(/hod\.html/);
  await expect(page.locator('body')).not.toContainText(/permission denied|not authorized|access denied/i);

  // But unlike before, the KPI card never gets real data: loadPortalData()'s
  // Promise.all rejects on the very first 403 it hits, so cachedSummary is
  // never reassigned from its zeroed initial value.
  const activeRooms = await page.locator('.metric-card', { hasText: 'Active Rooms' }).locator('.metric-number').innerText();
  expect(Number(activeRooms)).toBe(0);
});

test('UI: a doctor can still navigate straight to staff.html and get the full reception portal -- /patients/ and /allocations genuinely have no role restriction, so this part is unchanged', async ({ page }) => {
  await loginAs(page, 'doctor');

  await page.goto('/staff.html');
  await page.waitForLoadState('networkidle');

  await expect(page).toHaveURL(/staff\.html/);
  await expect(page.locator('body')).not.toContainText(/permission denied|not authorized|access denied/i);
  expect(await page.locator('.nav-btn').count()).toBeGreaterThan(0);
  expect(await page.title()).toBe('AFID Dental Staff Portal');
});

test('API: a receptionist token now gets a real 403 from every HOD read endpoint -- GET /hod/summary, GET /hod/rooms, GET /staff/', async ({ request }) => {
  const headers = await apiLogin(request, 'receptionist');

  const [summaryRes, roomsRes, staffRes] = await Promise.all([
    request.get(`${API}/hod/summary`, { headers }),
    request.get(`${API}/hod/rooms`, { headers }),
    request.get(`${API}/staff/`, { headers }),
  ]);

  expect(summaryRes.status()).toBe(403);
  expect(roomsRes.status()).toBe(403);
  expect(staffRes.status()).toBe(403);
});

test('API: a receptionist token can no longer create an operatory room -- POST /hod/rooms now 403s and no room is actually created', async ({ request }) => {
  const headers = await apiLogin(request, 'receptionist');
  const roomName = uniqueId('QA Route-Guard Room');

  const createRes = await request.post(`${API}/hod/rooms`, {
    headers,
    data: { room_name: roomName, assigned_doctor: null, current_case: null, queue_count: 0 },
  });
  expect(createRes.status()).toBe(403);

  const hodHeaders = await apiLogin(request, 'hod');
  const after = await (await request.get(`${API}/hod/rooms`, { headers: hodHeaders })).json();
  expect(after.some((r: any) => r.room_name === roomName)).toBe(false);
});

test('API: a receptionist token can no longer CRUD the staff directory -- POST /staff/ now 403s', async ({ request }) => {
  const headers = await apiLogin(request, 'receptionist');
  const staffName = uniqueId('QA Route-Guard Staff');

  const createRes = await request.post(`${API}/staff/`, {
    headers,
    data: { name: staffName, role: 'Nurse', status: 'Active' },
  });
  expect(createRes.status()).toBe(403);
});

test('API: GET /hod/timeline/{mr} deliberately allows doctor AND receptionist too, unlike the rest of /hod -- both the doctor and reception portals have their own Patient Timeline page that reads from it', async ({ page, request }) => {
  await loginAs(page, 'receptionist');
  const seedHeaders = await apiLogin(request, 'receptionist');
  const patientRes = await request.post(`${API}/patients/`, {
    headers: seedHeaders,
    data: {
      mr_number: uniqueId('QA-MR'),
      file_number: uniqueId('QA-F'),
      full_name: 'QA Route-Guard Timeline Patient',
      cnic: '12121-1212121-1',
      room: 'Room 10',
      assigned_doctor: 'Dr. Asadullah Khan',
      procedure_category: 'Consultation',
    },
  });
  const patient = await patientRes.json();

  const doctorHeaders = await apiLogin(request, 'doctor');
  const timelineRes = await request.get(`${API}/hod/timeline/${encodeURIComponent(patient.mr_number)}`, { headers: doctorHeaders });
  expect(timelineRes.status()).toBe(200);

  // Receptionist genuinely needs this too -- staff.html's own reception-side
  // "Patient Timeline" page reads from this exact endpoint. This used to
  // 403 unconditionally, which the frontend's try/catch silently swallowed
  // into an empty timeline -- indistinguishable from a patient with
  // genuinely no steps (see tests/timeline/patient-timeline.spec.ts for the
  // test that caught this).
  const receptionistTimelineRes = await request.get(`${API}/hod/timeline/${encodeURIComponent(patient.mr_number)}`, { headers: seedHeaders });
  expect(receptionistTimelineRes.status()).toBe(200);
});

test('contrast/positive control: PATCH /leaves/{id}/status still correctly 403s a receptionist -- this check was already correct before, and is now the model the endpoints above follow', async ({ request }) => {
  const headers = await apiLogin(request, 'receptionist');
  await clearOwnPendingLeaves(request, headers);

  const submitRes = await request.post(`${API}/leaves/`, {
    headers,
    data: {
      leave_type: 'Casual Leave',
      coverage_officer: 'QA Coverage Officer',
      reason: uniqueId('QA route-guard contrast leave'),
      ...futureLeaveWindow(1),
    },
  });
  expect(submitRes.status()).toBe(201);
  const leave = await submitRes.json();

  const approveRes = await request.patch(`${API}/leaves/${leave.id}/status`, {
    headers,
    data: { status: 'APPROVED' },
  });
  expect(approveRes.status()).toBe(403);
  expect((await approveRes.json()).detail).toBe('Only HOD or Admin can approve/reject leave');
});
