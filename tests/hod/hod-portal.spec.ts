import { test, expect } from '../fixtures/helpers';
import { loginAs, authHeaders, uniqueId } from '../fixtures/helpers';

const API = 'http://localhost:8000';

// Grounded in a fresh read of hod.html against the CURRENT checkout. Several
// of the old scaffold's findings here are fixed; one new one is confirmed:
//
//   - schemas.LeaveOut's requester_name field IS populated by the real API:
//     routers/leaves.py's serialize_leave() does
//     `requester_name: leave.requester.full_name if leave.requester else None`,
//     backed by a joinedload(LeaveRequest.requester) in list_leaves(). So
//     hod.html's `requester_name: l.requester_name || \`User #${l.requester_id}\``
//     fallback (loadPortalData()) is never actually triggered in practice --
//     the real requester name shows up directly. The fallback logic stays in
//     the app as a defensive measure for an edge case (e.g. a leave whose
//     requester user was since deleted), but under normal operation the old
//     literal "Unknown" text, and even the more-informative "User #<id>"
//     placeholder, are never shown.
//   - handleLeaveResolve() now calls `api.patch(..., { status: status.toUpperCase() })`
//     with an already-uppercase 'APPROVED'/'REJECTED' argument -- matching
//     LeaveStatus's exact casing. The old case-mismatch bug (title-case
//     'Approved' sent, enum expects 'APPROVED') is fixed: Approve/Reject now
//     genuinely work.
//   - approveExtension()/completeProcedure() now DO call a real
//     PATCH /hod/rooms/{id} (the old "UI-only, backend never hears about it"
//     gap is fixed for approveExtension(), which only ever sends
//     {approved: true}). completeProcedure() sends
//     {status: 'Available', ...} -- a fresh read of hod.html confirms this
//     is already correctly-cased to match RoomStatus's real enum value
//     exactly (not the lowercase 'available' this file used to assume), so
//     the PATCH genuinely succeeds and Room 10's backend status really does
//     transition to Available. That's a real, working fix -- not the
//     silent case-mismatch failure this test used to document.
//   - handleLeaveResolve() calls `showToast(...)` BEFORE awaiting its PATCH
//     call, not after -- so waiting on #toast-el proves nothing about
//     whether the request has actually completed. cachedLeaves is only
//     filtered (and the row removed) after a successful await, which is the
//     reliable completion signal to wait on instead.

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

test('Leave Management now shows the real requester name -- routers/leaves.py\'s serialize_leave() populates requester_name from the joined User row, so neither the old "Unknown" placeholder nor the "User #<id>" fallback ever actually appears', async ({ page, request }) => {
  const reason = uniqueId('QA leave reason');
  const { leave } = await submitLeaveAsDoctor(page, request, reason);
  expect(leave.requester_id).toBeTruthy();
  // NOTE: POST /leaves/ returns schemas.LeaveOut built directly off the raw
  // ORM object via response_model's automatic from_attributes serialization
  // -- requester_name isn't a real column on models.LeaveRequest, so
  // leave.requester_name comes back null here even though the real name IS
  // populated elsewhere. Only GET /leaves/'s serialize_leave() manually
  // joins and fills it in -- that's what hod.html's Leave Management page
  // actually reads from, so it's checked below via the rendered row
  // instead of this create response.

  await loginAs(page, 'hod');
  await page.click('text=Leave Management');

  const row = page.locator('tbody tr', { hasText: reason });
  await expect(row).toBeVisible();
  await expect(row).toContainText('Dr. Asadullah Khan');
  await expect(row).not.toContainText('Unknown');
  await expect(row).not.toContainText(`User #${leave.requester_id}`);
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

  // handleLeaveResolve() shows its "Updating..." toast optimistically,
  // BEFORE awaiting the PATCH -- so waiting on #toast-el is not a reliable
  // signal that the request has actually completed, and racing it against
  // a separate API assertion is flaky. cachedLeaves is only filtered (and
  // the row removed) AFTER a successful await, so wait on the row's
  // disappearance instead -- the real completion signal, with expect()'s
  // auto-retry giving the request time to finish.
  await expect(page.locator('tbody tr', { hasText: reason })).toHaveCount(0);

  const res = await request.get(`${API}/leaves/${leave.id}`, { headers: hodHeaders });
  const approved = await res.json();
  expect(approved.status).toBe('APPROVED');
  expect(approved.reviewed_by).toBeTruthy();
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

test('clicking "Complete" on a room now genuinely persists to the backend -- PATCH /hod/rooms/{id} sends the correctly-cased "Available" status, matching RoomStatus\'s enum value exactly, so the room really does transition out of Busy', async ({ page, request }) => {
  await loginAs(page, 'hod');
  const headers = await authHeaders(page);

  const before = await (await request.get(`${API}/hod/rooms`, { headers })).json();
  const room10Before = before.find((r: any) => r.room_name === 'Room 10');
  expect(room10Before).toBeTruthy();

  // Room 10 is seeded busy in init_db.py, but that script only ever runs
  // once and nothing resets operatory-room status between suite runs
  // (unlike patients, which the qaPatientCleanup fixture sweeps after every
  // test) -- this is a shared, non-isolated dev database, so its status can
  // genuinely drift over time. Ensure the precondition directly instead of
  // assuming it.
  const BUSY_STATUS = 'Busy (In-Procedure)';
  if (room10Before.status !== BUSY_STATUS) {
    await request.patch(`${API}/hod/rooms/${room10Before.id}`, { headers, data: { status: BUSY_STATUS } });
    await page.reload();
    await page.waitForLoadState('networkidle');
  }

  const roomRow = page.locator('tbody tr', { hasText: 'Room 10' });
  await roomRow.locator('button', { hasText: 'Complete' }).click();

  // completeProcedure() only sets room.status_display = 'Available' (and
  // resets time_in_mins to 0) AFTER its PATCH successfully resolves -- on
  // the catch path (a real backend error, or a transient hiccup on this
  // shared, non-isolated dev DB) it never touches status_display at all,
  // it just shows an error toast instead. Waiting on #toast-el alone can't
  // tell those two outcomes apart, since the catch branch shows a toast
  // too -- it was only ever a reliable "the await resolved" signal, not a
  // "the update succeeded" signal. Waiting for the row's own rendered
  // status to flip to "Available" is tied to the actual success path, and
  // as an auto-retrying assertion it also gives a brief, genuine window for
  // the PATCH to land before the backend is checked directly below.
  await expect(roomRow).toContainText('Available (0m)');

  const after = await (await request.get(`${API}/hod/rooms`, { headers })).json();
  const room10After = after.find((r: any) => r.room_name === 'Room 10');
  expect(room10After.status).toBe('Available');
  expect(room10After.current_case).toBe('Idle / Preparing Chair');
  expect(room10After.queue_count).toBe(0);
});
