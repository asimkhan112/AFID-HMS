import { test, expect } from '@playwright/test';
import { loginAs, authHeaders, uniqueId } from '../fixtures/helpers';

const API = 'http://localhost:8000';

// Grounded in a fresh read of doctor (1).html's handleLeaveSubmit() against
// the CURRENT checkout -- unchanged from the old scaffold's checkout in
// every respect that matters here: leave_type is still silently hardcoded to
// 'Casual Leave' (there is still no #leave-type control anywhere in the
// DOM), routers/leaves.py still 400s a backwards date range with the same
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

  let dialogMessage = '';
  page.once('dialog', async (dialog) => {
    dialogMessage = dialog.message();
    await dialog.accept();
  });

  await fillLeaveForm(page, { start: '2026-09-01', end: '2026-09-05', officer, reason });
  await page.click('button:has-text("Submit Request to HOD")');

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

test('the leave-type is silently hardcoded to "Casual Leave" -- the UI has no control to request Annual Leave or Medical Allocation at all', async ({ page, request }) => {
  await loginAs(page, 'doctor');
  await page.click('[data-page="leave"]');

  await expect(page.locator('select#leave-type')).toHaveCount(0);
  await expect(page.locator('[id*="leave-type" i]')).toHaveCount(0);
  await expect(page.locator('form:has(#leave-reason)')).not.toContainText(/annual leave/i);
  await expect(page.locator('form:has(#leave-reason)')).not.toContainText(/medical allocation/i);

  const reason = uniqueId('QA leave-type reason');
  page.once('dialog', (dialog) => dialog.accept());
  await fillLeaveForm(page, { start: '2026-09-10', end: '2026-09-11', officer: 'Maj. T. Farooq', reason });
  await page.click('button:has-text("Submit Request to HOD")');
  await expect(page.locator('tbody tr', { hasText: reason })).toBeVisible();

  const headers = await authHeaders(page);
  const res = await request.get(`${API}/leaves/`, { headers });
  const leaves = await res.json();
  const created = leaves.find((l: any) => l.reason === reason);
  expect(created.leave_type).toBe('Casual Leave');
});

test('an end date before the start date is rejected by the backend, and the doctor only finds out via a raw alert with the server\'s error text', async ({ page }) => {
  await loginAs(page, 'doctor');
  await page.click('[data-page="leave"]');

  let dialogMessage = '';
  page.once('dialog', async (dialog) => {
    dialogMessage = dialog.message();
    await dialog.accept();
  });

  await fillLeaveForm(page, {
    start: '2026-09-20',
    end: '2026-09-15', // before the start date
    officer: 'Maj. T. Farooq',
    reason: uniqueId('QA backwards-range reason'),
  });
  await page.click('button:has-text("Submit Request to HOD")');

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
