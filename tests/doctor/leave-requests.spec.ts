import { test, expect } from '../fixtures/helpers';
import { loginAs, authHeaders, uniqueId, DIALOG, acceptDialog, dialogText } from '../fixtures/helpers';

const API = 'http://localhost:8000';

// Grounded in a fresh read of doctor (1).html's handleLeaveSubmit() against
// the CURRENT checkout. What changed since this file was last grounded:
//
// 1. Feedback is no longer window.alert(). A successful submission shows an
//    in-page toast and repaints the leave log; a rejected one shows the
//    in-page `.afid-dlg` dialog (api.js uiAlert/uiError). Native dialogs were
//    replaced because the browser prefixes them with the page origin
//    ("localhost:5173 says…"), which reads as a browser warning rather than
//    part of the application.
//
// 2. A start date in the past is now refused -- both by a `min` attribute on
//    #leave-start-date and by routers/leaves.py. Tests therefore build their
//    dates relative to today rather than hardcoding calendar dates.
//
// 3. The backend refuses a second PENDING request that OVERLAPS an existing
//    one from the same requester (that duplicate-suppression is what stops one
//    request appearing repeatedly in the HOD's approval queue). Each test here
//    consequently books a distinct, non-overlapping window.
//
// 4. Only the leave-log TABLE is repainted after a refresh, never the whole
//    view -- a full re-render landing mid-typing would wipe the form.
//
// The leave-type <select> and its three models.LeaveType values are unchanged,
// as is the backwards-date-range rejection, and every field still carries
// `required` so the browser's own constraint validation blocks an incomplete
// form before handleLeaveSubmit() runs.

/** A date `offsetDays` from today, as YYYY-MM-DD. */
function dayOffset(offsetDays: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

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

  // Unique, far-out window so repeat runs never collide with the backend's
  // overlapping-pending-request guard.
  const offset = 200 + Math.floor(Math.random() * 400);
  await fillLeaveForm(page, { start: dayOffset(offset), end: dayOffset(offset + 4), officer, reason });

  await page.click('button:has-text("Submit Request to HOD")');

  // Success is an in-page toast, and the log table is repainted from the
  // server -- no native dialog is involved any more.
  await expect(page.locator(DIALOG)).toHaveCount(0);

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
  const offset = 700 + Math.floor(Math.random() * 400);
  await fillLeaveForm(page, { start: dayOffset(offset), end: dayOffset(offset + 1), officer: 'Maj. T. Farooq', reason });
  // Deliberately pick a NON-default option -- if leave_type were still
  // silently hardcoded to 'Casual Leave' under the hood, this is what would
  // expose it.
  await leaveTypeSelect.selectOption('Annual Leave');

  await page.click('button:has-text("Submit Request to HOD")');
  await expect(page.locator('tbody tr', { hasText: reason })).toBeVisible({ timeout: 15000 });

  const headers = await authHeaders(page);
  const res = await request.get(`${API}/leaves/`, { headers });
  const leaves = await res.json();
  const created = leaves.find((l: any) => l.reason === reason);
  expect(created.leave_type).toBe('Annual Leave');
});

test('an end date before the start date is rejected, and the doctor is told so in an in-page dialog rather than a native alert', async ({ page }) => {
  await loginAs(page, 'doctor');
  await page.click('[data-page="leave"]');

  let nativeDialogFired = false;
  page.on('dialog', async (d) => { nativeDialogFired = true; await d.dismiss(); });

  await fillLeaveForm(page, {
    start: dayOffset(20),
    end: dayOffset(15), // before the start date
    officer: 'Maj. T. Farooq',
    reason: uniqueId('QA backwards-range reason'),
  });

  await page.click('button:has-text("Submit Request to HOD")');

  await expect(page.locator(DIALOG)).toBeVisible({ timeout: 10000 });
  expect(await dialogText(page)).toContain('End date must be on or after the start date');
  await acceptDialog(page);

  // No "<origin> says" browser popup.
  expect(nativeDialogFired).toBe(false);
});

test('a start date that has already passed is refused instead of being accepted as a live request', async ({ page }) => {
  await loginAs(page, 'doctor');
  await page.click('[data-page="leave"]');

  // The picker itself now carries a lower bound.
  expect(await page.locator('#leave-start-date').getAttribute('min')).toBe(dayOffset(0));

  // Force a past value the way a determined user could, and confirm it is
  // still rejected rather than filed.
  await page.evaluate(() => {
    const el = document.getElementById('leave-start-date') as HTMLInputElement;
    el.removeAttribute('min');
    el.value = '2020-01-01';
  });
  const reason = uniqueId('QA past-start reason');
  await fillLeaveForm(page, { end: dayOffset(5), officer: 'Maj. T. Farooq', reason });

  let leavePostSeen = false;
  page.on('request', (req) => {
    if (req.method() === 'POST' && req.url().endsWith('/leaves/')) leavePostSeen = true;
  });

  await page.click('button:has-text("Submit Request to HOD")');

  await expect(page.locator(DIALOG)).toBeVisible({ timeout: 10000 });
  expect(await dialogText(page)).toContain('already passed');
  await acceptDialog(page);

  // Rejected client-side -- it never even reaches the backend.
  expect(leavePostSeen).toBe(false);
  await expect(page.locator('tbody tr', { hasText: reason })).toHaveCount(0);
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
  await fillLeaveForm(page, { start: dayOffset(25), end: dayOffset(26), officer }); // reason left blank
  await page.click('button:has-text("Submit Request to HOD")');
  await page.waitForTimeout(500);

  expect(dialogFired).toBe(false);
  expect(leavePostSeen).toBe(false);
  await expect(page.locator('tbody tr', { hasText: officer })).toHaveCount(0);
});
