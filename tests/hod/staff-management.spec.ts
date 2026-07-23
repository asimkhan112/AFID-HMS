import { test, expect } from '@playwright/test';
import { loginAs, authHeaders, uniqueId } from '../fixtures/helpers';

const API = 'http://localhost:8000';

// Grounded in a fresh read of hod.html's renderStaffMgmtView() against the
// CURRENT checkout -- unchanged from the old scaffold's checkout in every
// respect that matters here. routers/staff.py and routers/hod.py now both
// sit behind require_role(hod, admin) (see tests/auth/route-guards.spec.ts
// for that fix), but every test in this file already authenticates as
// 'hod', so none of it is affected by that change.

function staffRegistryCard(page: import('@playwright/test').Page) {
  return page.locator('.container-card', { hasText: 'Staff Registry' });
}

test('HOD Staff Management renders the full seeded Staff Directory, not a subset or fallback list', async ({ page, request }) => {
  await loginAs(page, 'hod');
  const headers = await authHeaders(page);
  const staff = await (await request.get(`${API}/staff/`, { headers })).json();
  expect(staff.length).toBeGreaterThan(0);

  await page.click('text=Staff Management');
  const card = staffRegistryCard(page);
  await expect(card.locator('tbody tr')).toHaveCount(staff.length);

  // Spot-check a couple of real seeded rows by name/role/status.
  const sara = staff.find((s: any) => s.name === 'Sara Khan');
  if (sara) {
    const row = card.locator('tbody tr', { hasText: 'Sara Khan' });
    await expect(row).toContainText(sara.role);
    await expect(row).toContainText(sara.status);
  }
});

test('the role filter treats "On Leave" as if it were a job role, because at least one staff row has role and status set to the exact same string', async ({ page, request }) => {
  await loginAs(page, 'hod');
  const headers = await authHeaders(page);
  const staff = await (await request.get(`${API}/staff/`, { headers })).json();
  const onLeaveByRole = staff.filter((s: any) => s.role === 'On Leave');
  test.skip(onLeaveByRole.length === 0, 'seed data no longer has a staff row whose role equals "On Leave" -- nothing to prove here');

  await page.click('text=Staff Management');
  const card = staffRegistryCard(page);
  const select = card.locator('select');
  await expect(select.locator('option', { hasText: 'On Leave' })).toHaveCount(1);

  await select.selectOption('On Leave');
  await expect(card.locator('tbody tr')).toHaveCount(onLeaveByRole.length);
  for (const s of onLeaveByRole) {
    await expect(card.locator('tbody tr', { hasText: s.name })).toBeVisible();
  }
});

test('Staff Management has no create/edit/delete controls anywhere -- it is read-only even though POST/PUT/DELETE /staff/ all work correctly on the backend for an HOD token', async ({ page, request }) => {
  await loginAs(page, 'hod');
  await page.click('text=Staff Management');
  const card = staffRegistryCard(page);

  await expect(card.getByRole('button', { name: /add|create|new|edit|delete|remove/i })).toHaveCount(0);
  await expect(card.locator('input[type=text], input:not([type])')).toHaveCount(0);
  await expect(card.locator('form')).toHaveCount(0);

  // Prove the backend side is real and functional for a properly-authorized
  // (HOD) token, in contrast to the UI.
  const headers = await authHeaders(page);
  const name = uniqueId('QA Staff Member');
  const createRes = await request.post(`${API}/staff/`, { headers, data: { name, role: 'Technician', status: 'Active' } });
  expect(createRes.status()).toBe(201);
  const created = await createRes.json();
  expect(created.name).toBe(name);

  const deleteRes = await request.delete(`${API}/staff/${created.id}`, { headers });
  expect(deleteRes.status()).toBe(204);
});

test('POST /hod/rooms works and creates a real new operatory room for an HOD token, but Overview has no "Add Room" control anywhere to reach it through the UI', async ({ page, request }) => {
  await loginAs(page, 'hod');
  const headers = await authHeaders(page);

  const roomName = uniqueId('QA-Room');
  const before = await (await request.get(`${API}/hod/rooms`, { headers })).json();
  expect(before.some((r: any) => r.room_name === roomName)).toBe(false);

  const createRes = await request.post(`${API}/hod/rooms`, {
    headers,
    data: { room_name: roomName, assigned_doctor: null, current_case: null, queue_count: 0 },
  });
  expect(createRes.status()).toBe(201);
  const created = await createRes.json();
  expect(created.room_name).toBe(roomName);
  expect(created.status).toBe('Available');

  const after = await (await request.get(`${API}/hod/rooms`, { headers })).json();
  expect(after.some((r: any) => r.room_name === roomName)).toBe(true);

  // Meanwhile the UI has no path to this at all.
  await page.click('text=Overview');
  const overviewCard = page.locator('.container-card', { hasText: 'Operatory Room Status' });
  await expect(overviewCard.getByRole('button', { name: /add|create|new room/i })).toHaveCount(0);
  // The newly-created room doesn't even show up without a reload, since
  // loadPortalData() only runs once at page load.
  await expect(overviewCard.locator('tbody tr', { hasText: roomName })).toHaveCount(0);
});
