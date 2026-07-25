import { test, expect } from '../fixtures/helpers';
import { loginAs, authHeaders, uniqueId } from '../fixtures/helpers';

const API = 'http://localhost:8000';

// Grounded in a fresh read of doctor (1).html's handleLeaveSubmit() against
// the CURRENT checkout. Two things changed since this file was last
// grounded, both confirmed against the live source rather than assumed:
//
// 1. The form now has a real #leave-type <select> (Casual Leave / Annual
//    Leave / Medical Allocation) whose value flows straight through to
//    POST /leaves/'s leave_type field, and models.LeaveType's enum values
//    match those three option strings exactly -- the old "silently
//    hardcoded to Casual Leave" bug is fixed. The test that used to assert
//    this control didn't exist has been rewritten to prove it now works.
//
// 2. handleLeaveSubmit() is async and awaits its POST /leaves/ call before
//    ever calling alert(...). page.click() resolves once the click is
//    dispatched -- it does NOT wait for that async handler to finish -- so
//    a plain expect() checked immediately afterward can race ahead of the
//    alert firing and see dialogMessage still at its initial ''. Tests
//    here now register page.waitForEvent('dialog') before the click and
//    await it afterward, instead of a bare page.once('dialog', ...) +
//    immediate assert.
//
// routers/leaves.py still 400s a backwards date range with the same
// message, and every form field still carries `required`, so the browser's
// own constraint validation still blocks submission of an incomplete form
// before handleLeaveSubmit()'s own blank-field alert can ever fire.

async function fillLeaveForm(
  page: import('@playwright/test').Page,
  opts: { start?: string; end?: string; officer?: string; reason?: string }
) {
  if (opts.start !== undefined) await page.fill('#leave-start-date', opts.start);
  if (opts.end !== undefined) await page.fill('#leave-end-date', opts.end);
  if (opts.officer !== undefined) await page.fill('#leave-coverage-officer', opts.officer);
  if (opts.reason !== undefined) await page.fill('#leave-reason', opts.reason);
}

test('submitting a leave request through the UI posts to /leaves/ and lands at the top of "My Active Leave & Coverage Log" as PENDING', async ({ page, request }) => {
  await loginAs(page, 'doctor');
  await page.click('[data-page="leave"]');

  const officer = uniqueId('Maj. QA Officer');
  const reason = uniqueId('QA leave reason');

  await fillLeaveForm(page, { start: '2026-09-01', end: '2026-09-05', officer, reason });

  const dialogPromise = page.waitForEvent('dialog');
  await page.click('button:has-text("Submit Request to HOD")');
  const dialog = await dialogPromise;
  const dialogMessage = dialog.message();
  await dialog.accept();

  expect(dialogMessage).toBe('Leave request successfully sent to the HOD.');

  // handleLeaveSubmit() re-renders the "leave" view after the alert closes,
  // prepending the new leave to cachedMyLeaves.
  const row = page.locator('tbody tr', { hasText: reason });
  await expect(row).toBeVisible();
  await expect(row).toContainText(officer);
  await expect(row.locator('.badge')).toHaveClass(/badge-warning/);
  await expect(row.locator('.badge')).toHaveText('PENDING');

  const headers = await authHeaders(page);
  const res = await request.get(`${API}/leaves/`, { headers });
  const leaves = await res.json();
  const created = leaves.find((l: any) => l.reason === reason);
  expect(created).toBeTruthy();
  expect(created.coverage_officer).toBe(officer);
  expect(created.status).toBe('PENDING');
});

test('the leave-type dropdown offers Casual Leave, Annual Leave, and Medical Allocation, and whichever one the doctor picks round-trips correctly to the backend', async ({ page, request }) => {
  await loginAs(page, 'doctor');
  await page.click('[data-page="leave"]');

  // models.LeaveType's three enum values, in the exact strings the backend
  // expects -- confirmed against a fresh read of AFID backend/models.py.
  const leaveTypeSelect = page.locator('select#leave-type');
  await expect(leaveTypeSelect).toBeVisible();
  const optionLabels = await leaveTypeSelect.locator('option').allTextContents();
  expect(optionLabels).toEqual(['Casual Leave', 'Annual Leave', 'Medical Allocation']);

  const reason = uniqueId('QA leave-type reason');
  await fillLeaveForm(page, { start: '2026-09-10', end: '2026-09-11', officer: 'Maj. T. Farooq', reason });
  // Deliberately pick a NON-default option -- if leave_type were still
  // silently hardcoded to 'Casual Leave' under the hood, this is what would
  // expose it.
  await leaveTypeSelect.selectOption('Annual Leave');

  const dialogPromise = page.waitForEvent('dialog');
  await page.click('button:has-text("Submit Request to HOD")');
  const dialog = await dialogPromise;
  await dialog.accept();
  await expect(page.locator('tbody tr', { hasText: reason })).toBeVisible();

  const headers = await authHeaders(page);
  const res = await request.get(`${API}/leaves/`, { headers });
  const leaves = await res.json();
  const created = leaves.find((l: any) => l.reason === reason);
  expect(created.leave_type).toBe('Annual Leave');
});

test('an end date before the start date is rejected by the backend, and the doctor only finds out via a raw alert with the server\'s error text', async ({ page }) => {
  await loginAs(page, 'doctor');
  await page.click('[data-page="leave"]');

  await fillLeaveForm(page, {
    start: '2026-09-20',
    end: '2026-09-15', // before the start date
    officer: 'Maj. T. Farooq',
    reason: uniqueId('QA backwards-range reason'),
  });

  const dialogPromise = page.waitForEvent('dialog');
  await page.click('button:has-text("Submit Request to HOD")');
  const dialog = await dialogPromise;
  const dialogMessage = dialog.message();
  await dialog.accept();

  expect(dialogMessage).toBe('Error submitting leave request: End date must be on or after start date');
});

test('leaving a required field blank never even reaches handleLeaveSubmit() -- native HTML5 validation silently blocks the whole form, so the "Please complete all leave fields" alert can never actually fire', async ({ page }) => {
  await loginAs(page, 'doctor');
  await page.click('[data-page="leave"]');

  let dialogFired = false;
  page.on('dialog', async (dialog) => { dialogFired = true; await dialog.accept(); });
  let leavePostSeen = false;
  page.on('request', (req) => {
    if (req.method() === 'POST' && req.url().endsWith('/leaves/')) leavePostSeen = true;
  });

  const officer = uniqueId('Maj. QA Never-Submitted');
  await fillLeaveForm(page, { start: '2026-09-25', end: '2026-09-26', officer }); // reason left blank
  await page.click('button:has-text("Submit Request to HOD")');
  await page.waitForTimeout(500);

  expect(dialogFired).toBe(false);
  expect(leavePostSeen).toBe(false);
  await expect(page.locator('tbody tr', { hasText: officer })).toHaveCount(0);
});
