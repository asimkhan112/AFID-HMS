import { test, expect } from '@playwright/test';
import { loginAs, authHeaders, uniqueId } from '../fixtures/helpers';

const API = 'http://localhost:8000';

// Grounded in a fresh read of hod.html against the CURRENT checkout. Several
// of the old scaffold's findings here are fixed; one new one is confirmed:
//
//   - schemas.LeaveOut now HAS a requester_name field, but nothing in
//     routers/leaves.py's list_leaves()/ORM populates it, so it's still
//     always None from the real API. hod.html's loadPortalData() maps
//     `requester_name: l.requester_name || \`User #${l.requester_id}\``,
//     so the fallback text changed from the literal "Unknown" to a more
//     informative "User #<id>" -- still not the requester's real name, but
//     a genuine improvement.
//   - handleLeaveResolve() now calls `api.patch(..., { status: status.toUpperCase() })`
//     with an already-uppercase 'APPROVED'/'REJECTED' argument -- matching
//     LeaveStatus's exact casing. The old case-mismatch bug (title-case
//     'Approved' sent, enum expects 'APPROVED') is fixed: Approve/Reject now
//     genuinely work.
//   - approveExtension()/completeProcedure() now DO call a real
//     PATCH /hod/rooms/{id} (the old "UI-only, backend never hears about it"
//     gap is fixed for approveExtension(), which only ever sends
//     {approved: true}). completeProcedure() specifically sends
//     {status: 'available', ...} -- but RoomStatus's real value is
//     "Available" (capitalized), and this app's Enum columns are confirmed
//     case-sensitive elsewhere (patients: WAITING/ACTIVE/COMPLETED). So this
//     one PATCH call is expected to fail server-side on the case mismatch,
//     leaving the room's real backend status unchanged even though the
//     button now genuinely attempts to persist it.

async function submitLeaveAsDoctor(page: import('@playwright/test').Page, request: import('@playwright/test').APIRequestContext, reason: string) {
  await loginAs(page, 'doctor');
  const headers = await authHeaders(page);
  const res = await request.post(`${API}/leaves/`, {
    headers,
    data: {
      leave_type: 'Casual Leave',
      coverage_officer: 'Maj. T. Farooq',
      reason,
      start_date: '2026-08-01',
      end_date: '2026-08-03',
    },
  });
  return { leave: await res.json(), doctorHeaders: headers };
}

test('HOD login lands on Overview with live KPI metrics and operatory room status', async ({ page }) => {
  await loginAs(page, 'hod');

  await expect(page.locator('.nav-btn.active')).toContainText('Overview');
  await expect(page.locator('.metric-card', { hasText: 'Patients Today' })).toBeVisible();
  await expect(page.locator('.metric-card', { hasText: 'Doctors On Duty' })).toBeVisible();
  await expect(page.locator('.metric-card', { hasText: 'Active Rooms' })).toBeVisible();

  // Room 10 is seeded busy with Dr. Rehan M. -- confirm real backend data
  // reaches the Operatory Room Status table, not placeholder content.
  const roomRow = page.locator('tbody tr', { hasText: 'Room 10' });
  await expect(roomRow).toContainText('Dr. Rehan M.');
});

test('Leave Management now shows "User #<id>" as the requester instead of the old literal "Unknown" -- still not the requester\'s real name, but a more informative placeholder', async ({ page, request }) => {
  const reason = uniqueId('QA leave reason');
  const { leave } = await submitLeaveAsDoctor(page, request, reason);
  expect(leave.requester_id).toBeTruthy();

  await loginAs(page, 'hod');
  await page.click('text=Leave Management');

  const row = page.locator('tbody tr', { hasText: reason });
  await expect(row).toBeVisible();
  await expect(row).toContainText(`User #${leave.requester_id}`);
  await expect(row).not.toContainText('Unknown');
  await expect(row).not.toContainText('Dr. Asadullah Khan');
});

test('clicking "Approve" on a leave request now succeeds -- hod.html sends an already-uppercased status, matching LeaveStatus\'s exact casing, fixing the old case-mismatch bug', async ({ page, request }) => {
  const reason = uniqueId('QA approve reason');
  const { leave } = await submitLeaveAsDoctor(page, request, reason);
  expect(leave.status).toBe('PENDING');

  await loginAs(page, 'hod');
  const hodHeaders = await authHeaders(page);
  await page.click('text=Leave Management');

  const row = page.locator('tbody tr', { hasText: reason });
  await expect(row).toBeVisible();
  await row.locator('button', { hasText: 'Approve' }).click();

  await expect(page.locator('#toast-el')).toBeVisible();

  const res = await request.get(`${API}/leaves/${leave.id}`, { headers: hodHeaders });
  const approved = await res.json();
  expect(approved.status).toBe('APPROVED');
  expect(approved.reviewed_by).toBeTruthy();

  // handleLeaveResolve() removes it from cachedLeaves only on success, so
  // the row genuinely disappears from the still-pending list now.
  await expect(page.locator('tbody tr', { hasText: reason })).toHaveCount(0);
});

test('a direct API call with the correctly-cased status still gets approved -- confirms the endpoint itself was never the problem', async ({ page, request }) => {
  const reason = uniqueId('QA correct-case reason');
  const { leave } = await submitLeaveAsDoctor(page, request, reason);

  await loginAs(page, 'hod');
  const hodHeaders = await authHeaders(page);
  const res = await request.patch(`${API}/leaves/${leave.id}/status`, {
    headers: hodHeaders,
    data: { status: 'APPROVED' },
  });
  expect(res.status()).toBe(200);
  const approved = await res.json();
  expect(approved.status).toBe('APPROVED');
  expect(approved.reviewed_by).toBeTruthy();
});

test('a doctor cannot approve their own leave request directly via the API, even with correct casing', async ({ page, request }) => {
  const { leave, doctorHeaders } = await submitLeaveAsDoctor(page, request, uniqueId('QA self-approve reason'));

  const res = await request.patch(`${API}/leaves/${leave.id}/status`, {
    headers: doctorHeaders,
    data: { status: 'APPROVED' },
  });
  expect(res.status()).toBe(403);
});

test('clicking "Complete" on a room now attempts a real PATCH /hod/rooms/{id} call, but sends a lowercase status ("available") that doesn\'t match the RoomStatus enum\'s real value ("Available"), so the backend room status never actually changes', async ({ page, request }) => {
  await loginAs(page, 'hod');
  const headers = await authHeaders(page);

  const before = await (await request.get(`${API}/hod/rooms`, { headers })).json();
  const room10Before = before.find((r: any) => r.room_name === 'Room 10');
  expect(room10Before).toBeTruthy();
  const originalStatus = room10Before.status;

  const roomRow = page.locator('tbody tr', { hasText: 'Room 10' });
  await roomRow.locator('button', { hasText: 'Complete' }).click();
  await expect(page.locator('#toast-el')).toBeVisible();

  const after = await (await request.get(`${API}/hod/rooms`, { headers })).json();
  const room10After = after.find((r: any) => r.room_name === 'Room 10');
  expect(room10After.status).toBe(originalStatus);
});
