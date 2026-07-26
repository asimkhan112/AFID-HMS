import { test, expect, Page } from '@playwright/test';

/**
 * Browser-level regression coverage for the batch of portal defects reported
 * from clinic use (staff / doctor / HOD).
 *
 * Each test names the reported symptom it locks down.
 */

const CREDS = {
  receptionist: { email: 'reception@afid.mil', password: 'staff1234', page: 'staff.html' },
  doctor: { email: 'doctor@afid.mil', password: 'doctor1234', page: 'doctor (1).html' },
  hod: { email: 'hod@afid.mil', password: 'admin1234', page: 'hod.html' },
};

async function loginAs(page: Page, role: keyof typeof CREDS) {
  const { email, password } = CREDS[role];
  await page.goto('/Login.html');
  await page.evaluate(() => {
    localStorage.removeItem('afid_token');
    localStorage.removeItem('afid_user');
  });
  await page.goto('/Login.html');
  await page.fill('#login-email', email);
  await page.fill('#login-password', password);
  await page.click('#login-btn');
  await page.waitForFunction(() => !!localStorage.getItem('afid_token'), { timeout: 15000 });
}

/** Fail loudly if any native browser dialog fires — those render "<origin> says". */
function forbidNativeDialogs(page: Page, seen: string[]) {
  page.on('dialog', async (d) => {
    seen.push(`${d.type()}: ${d.message()}`);
    await d.dismiss().catch(() => {});
  });
}

test.describe('Staff portal', () => {
  test('patient registration exposes gender, blood group and service profile', async ({ page }) => {
    await loginAs(page, 'receptionist');
    await page.click('button[data-page="patient_reg"]');

    await expect(page.locator('#p-gender')).toBeVisible();
    await expect(page.locator('#p-blood')).toBeVisible();
    await expect(page.locator('#p-service-profile')).toBeVisible();

    // Real, selectable values — not empty placeholder dropdowns.
    expect(await page.locator('#p-gender option').count()).toBeGreaterThan(2);
    expect(await page.locator('#p-blood option').count()).toBeGreaterThan(5);
    expect(await page.locator('#p-service-profile option').count()).toBeGreaterThan(3);
  });

  test('assigned-room dropdown covers rooms 10-19, not just 15 and 16', async ({ page }) => {
    await loginAs(page, 'receptionist');
    await page.click('button[data-page="doctor_mgmt"]');

    const values = await page.locator('#d-room option').evaluateAll((opts) =>
      opts.map((o) => (o as HTMLOptionElement).value)
    );
    for (let r = 10; r <= 19; r++) {
      expect(values).toContain(`Room ${r}`);
    }
  });

  test('doctor management can register a real login account', async ({ page }) => {
    await loginAs(page, 'receptionist');
    await page.click('button[data-page="doctor_mgmt"]');

    // The form that creates credentials, not just a room-allocation row.
    await expect(page.locator('#dr-name')).toBeVisible();
    await expect(page.locator('#dr-email')).toBeVisible();
    await expect(page.locator('#dr-password')).toBeVisible();
  });

  test('a registered doctor can then sign in and reach their portal', async ({ page }) => {
    const tag = Date.now().toString(36);
    const name = `Dr. E2E ${tag}`;
    const email = `e2e.${tag}@afid.mil`;

    await loginAs(page, 'receptionist');
    await page.click('button[data-page="doctor_mgmt"]');
    await page.fill('#dr-name', name);
    await page.fill('#dr-email', email);
    await page.fill('#dr-password', 'doctor1234');
    await page.selectOption('#dr-room', '');
    await page.click('#doctor-register-form button[type="submit"]');

    // New account shows up in the live doctor matrix.
    await expect(page.locator('table', { hasText: name }).first()).toBeVisible({ timeout: 15000 });

    // …and the credentials actually work.
    await page.goto('/Login.html');
    await page.evaluate(() => {
      localStorage.removeItem('afid_token');
      localStorage.removeItem('afid_user');
    });
    await page.goto('/Login.html');
    await page.fill('#login-email', email);
    await page.fill('#login-password', 'doctor1234');
    await page.click('#login-btn');
    await expect(page).toHaveURL(/doctor%20\(1\)\.html$/, { timeout: 15000 });
  });

  // Rooms are an exclusive, finite resource (one doctor each, Rooms 10-19), so
  // this test reserves two specific rooms up front and releases them again --
  // otherwise repeat runs leak allocations and eventually exhaust the ward.
  test('re-allocating a doctor moves them instead of listing two rooms', async ({ page, request }) => {
    const tag = Date.now().toString(36);
    const name = `Dr. Room ${tag}`;
    const roomA = 'Room 18';
    const roomB = 'Room 19';

    const login = await request.post('http://127.0.0.1:8000/auth/login', {
      data: { email: CREDS.receptionist.email, password: CREDS.receptionist.password },
    });
    const token = (await login.json()).access_token;
    const auth = { Authorization: `Bearer ${token}` };

    const clearRooms = async () => {
      const res = await request.get('http://127.0.0.1:8000/allocations', { headers: auth });
      for (const a of await res.json()) {
        if (a.room === roomA || a.room === roomB || a.doctor_name === name) {
          await request.delete(`http://127.0.0.1:8000/allocations/${a.id}`, { headers: auth });
        }
      }
    };
    await clearRooms();

    try {
      await loginAs(page, 'receptionist');
      await page.click('button[data-page="doctor_mgmt"]');
      await page.fill('#dr-name', name);
      await page.fill('#dr-email', `room.${tag}@afid.mil`);
      await page.fill('#dr-password', 'doctor1234');
      await page.click('#doctor-register-form button[type="submit"]');
      await expect(page.locator(`tr:has-text("${name}")`)).toHaveCount(1, { timeout: 15000 });

      // First allocation.
      await page.selectOption('#d-name', name);
      await page.selectOption('#d-room', roomA);
      await page.click('#doctor-form button[type="submit"]');
      await expect(page.locator(`tr:has-text("${name}")`)).toContainText(roomA, { timeout: 15000 });

      // Re-allocate the SAME doctor to a different room.
      await page.selectOption('#d-name', name);
      await page.selectOption('#d-room', roomB);
      await page.click('#doctor-form button[type="submit"]');

      // Exactly ONE row for this doctor, showing the NEW room only.
      await expect(page.locator(`tr:has-text("${name}")`)).toHaveCount(1, { timeout: 15000 });
      const row = page.locator(`tr:has-text("${name}")`);
      await expect(row).toContainText(roomB);
      await expect(row).not.toContainText(roomA);
    } finally {
      await clearRooms();
    }
  });

  test('an allocated room can be released again', async ({ page, request }) => {
    const tag = Date.now().toString(36);
    const name = `Dr. Release ${tag}`;
    const room = 'Room 17';

    const login = await request.post('http://127.0.0.1:8000/auth/login', {
      data: { email: CREDS.receptionist.email, password: CREDS.receptionist.password },
    });
    const token = (await login.json()).access_token;
    const auth = { Authorization: `Bearer ${token}` };

    const res = await request.get('http://127.0.0.1:8000/allocations', { headers: auth });
    for (const a of await res.json()) {
      if (a.room === room) await request.delete(`http://127.0.0.1:8000/allocations/${a.id}`, { headers: auth });
    }

    await request.post('http://127.0.0.1:8000/auth/register', {
      data: { full_name: name, email: `release.${tag}@afid.mil`, password: 'doctor1234', role: 'doctor' },
    });
    await request.post('http://127.0.0.1:8000/allocations', {
      headers: auth, data: { doctor_name: name, room, department: 'Orthodontics' },
    });

    await loginAs(page, 'receptionist');
    await page.click('button[data-page="doctor_mgmt"]');
    const row = page.locator(`tr:has-text("${name}")`);
    await expect(row).toContainText(room, { timeout: 15000 });

    await row.locator('button:has-text("Release Room")').click();
    await page.locator('.afid-dlg-btn.primary').click();

    await expect(page.locator(`tr:has-text("${name}")`)).toContainText('Unallocated', { timeout: 15000 });
  });
});

test.describe('Doctor portal', () => {
  test('procedure dropdown is populated', async ({ page }) => {
    await loginAs(page, 'doctor');
    await page.click('.nav-item[data-page="operations"]');
    // Data-backed views wait for the initial load before painting, rather than
    // flashing an empty dropdown and then filling it in. The picker is
    // ATTACHED but not visible until a patient is opened (it lives on the
    // workspace screen), so don't wait on visibility here.
    await page.waitForSelector('#procedure-select', { state: 'attached', timeout: 15000 });
    await expect.poll(
      () => page.locator('#procedure-select option').count(),
      { timeout: 15000 }
    ).toBeGreaterThan(1);
  });

  test('leave request form is laid out with block labels and blocks past dates', async ({ page }) => {
    await loginAs(page, 'doctor');
    await page.click('.nav-item[data-page="leave"]');

    const start = page.locator('#leave-start-date');
    await expect(start).toBeVisible({ timeout: 15000 });

    // A `min` bound exists, so the date picker itself refuses past dates.
    const min = await start.getAttribute('min');
    expect(min).toBeTruthy();

    // Labels stack above their field rather than sitting inline beside it.
    const stacked = await page.evaluate(() => {
      const label = document.querySelector('label[for="leave-start-date"]') as HTMLElement;
      const input = document.getElementById('leave-start-date') as HTMLElement;
      if (!label || !input) return false;
      return input.getBoundingClientRect().top >= label.getBoundingClientRect().bottom - 1;
    });
    expect(stacked).toBe(true);
  });

  test('a past start date is rejected without a native browser dialog', async ({ page }) => {
    const dialogs: string[] = [];
    forbidNativeDialogs(page, dialogs);

    await loginAs(page, 'doctor');
    await page.click('.nav-item[data-page="leave"]');
    await page.waitForSelector('#leave-start-date', { timeout: 15000 });

    // Force a past value past the `min` attribute the way a determined user would.
    await page.evaluate(() => {
      const el = document.getElementById('leave-start-date') as HTMLInputElement;
      el.removeAttribute('min');
      el.value = '2020-01-01';
    });
    await page.fill('#leave-coverage-officer', 'Maj. Test');
    await page.fill('#leave-reason', 'Regression check');
    await page.click('form:has(#leave-reason) button[type="submit"]');

    // Rejected via the in-page dialog…
    await expect(page.locator('.afid-dlg')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('.afid-dlg-body')).toContainText('already passed');
    // …and no native popup (which would be prefixed with the page origin).
    expect(dialogs).toEqual([]);
  });

  test('analytics states its reporting period and keys rows by MR number', async ({ page }) => {
    await loginAs(page, 'doctor');
    await page.click('.nav-item[data-page="doctor-analytics"]');

    await expect(page.locator('#docAnalyticsPeriod')).toBeVisible({ timeout: 15000 });
    await expect(page.locator('#docAnalytics-personalCard')).toContainText('Reporting Period');
    await expect(page.locator('#docAnalytics-personalCard')).toContainText(/Week|Month|Days|All Time/);

    // The history table is keyed on MR No., not a generated CASE-nnn label.
    await expect(page.locator('th', { hasText: 'MR No.' }).first()).toBeVisible();
    const body = await page.locator('#docAnalyticsTableBody').innerText();
    expect(body).not.toMatch(/CASE-\d{3}/);
  });

  test('materials log updates quantity in place instead of duplicating the item', async ({ page }) => {
    await loginAs(page, 'doctor');
    await page.click('.nav-item[data-page="operations"]');
    await page.waitForSelector('#procedure-select option:not([disabled])', { state: 'attached', timeout: 15000 });

    // Reach the materials tab by selecting any procedure.
    const firstProc = await page.locator('#procedure-select option:not([disabled])').first().getAttribute('value');
    await page.evaluate(() => {
      (document.getElementById('view-search-screen') as HTMLElement).classList.remove('active');
      (document.getElementById('view-workspace-screen') as HTMLElement).classList.add('active');
    });
    await page.selectOption('#procedure-select', firstProc!);
    await page.click('button:has-text("Clinical Materials")');

    // Scope to the materials tab — the pharmacy tab has its own "+ Add".
    const addMaterial = page.locator('#subtab-materials button:has-text("+ Add")');

    await page.fill('#material-input', 'Regression Swab');
    await page.fill('#material-qty-input', '2');
    await addMaterial.click();
    await expect(page.locator('#materials-log-list')).toContainText('Regression Swab');

    // Re-adding the SAME item with a new quantity must not create a 2nd row.
    await page.fill('#material-input', 'Regression Swab');
    await page.fill('#material-qty-input', '9');
    await addMaterial.click();

    const rows = await page.locator('#materials-log-list .qty-row').evaluateAll((els) =>
      els.filter((e) => e.textContent?.includes('Regression Swab')).length
    );
    expect(rows).toBe(1);

    const qty = await page.locator('#materials-log-list .qty-row:has-text("Regression Swab") input').inputValue();
    expect(qty).toBe('9');
  });
});

test.describe('HOD portal', () => {
  test('patient operations is monitoring-only (no add-procedure control)', async ({ page }) => {
    await loginAs(page, 'hod');
    await page.waitForSelector('#nav-container .nav-btn');
    await page.click('.nav-btn:has-text("Patient Operations")');

    await expect(page.locator('button:has-text("+ Add Procedure")')).toHaveCount(0);
    await expect(page.locator('button:has-text("Confirm Time & Complete Session")')).toHaveCount(0);
    // The read-only banner appears on both the lookup and the workspace
    // screens; assert against the one that is actually on screen here.
    await expect(
      page.locator('#hod-view-search-screen').getByText('Monitoring — Read Only')
    ).toBeVisible();
  });

  test('opening a completed case reports COMPLETED, and does not flip its status', async ({ page, request }) => {
    // Seed a completed patient directly through the API.
    const tag = Date.now().toString(36);
    const login = await request.post('http://127.0.0.1:8000/auth/login', {
      data: { email: CREDS.receptionist.email, password: CREDS.receptionist.password },
    });
    const token = (await login.json()).access_token;
    const mr = `MR-HODQA-${tag}`;
    const created = await request.post('http://127.0.0.1:8000/patients/', {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        mr_number: mr, file_number: `F-HODQA-${tag}`, full_name: 'Capt. HOD Case',
        gender: 'Female', blood_group: 'A+', service_profile: 'Serving Officer',
        room: 'Room 12', assigned_doctor: 'Dr. Asadullah Khan', procedure_category: 'Consultation',
      },
    });
    const pid = (await created.json()).id;
    await request.patch(`http://127.0.0.1:8000/patients/${pid}/status`, {
      headers: { Authorization: `Bearer ${token}` }, data: { status: 'ACTIVE' },
    });
    await request.patch(`http://127.0.0.1:8000/patients/${pid}/status`, {
      headers: { Authorization: `Bearer ${token}` }, data: { status: 'COMPLETED' },
    });

    await loginAs(page, 'hod');
    await page.waitForSelector('#nav-container .nav-btn');
    await page.click('.nav-btn:has-text("Patient Operations")');
    await page.fill('#hod-patient-search-input', mr);
    await page.click('button:has-text("Search & Continue")');

    await expect(page.locator('#hod-val-status')).toContainText('COMPLETED', { timeout: 15000 });

    // Viewing must not mutate the record.
    const after = await request.get(`http://127.0.0.1:8000/patients/${pid}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect((await after.json()).status).toBe('COMPLETED');
  });

  test('a leave request is listed once, not repeatedly', async ({ page, request }) => {
    // Register a throwaway doctor so this test's leave dates cannot collide
    // with a pending request left behind by another run (which the overlap
    // guard would legitimately reject).
    const tag = Date.now().toString(36);
    const email = `leaveqa.${tag}@afid.mil`;
    const reg = await request.post('http://127.0.0.1:8000/auth/register', {
      data: { full_name: `Dr. Leave QA ${tag}`, email, password: 'doctor1234', role: 'doctor' },
    });
    expect(reg.status()).toBe(201);

    const login = await request.post('http://127.0.0.1:8000/auth/login', {
      data: { email, password: 'doctor1234' },
    });
    const token = (await login.json()).access_token;

    const start = new Date(Date.now() + 86400000 * 20).toISOString().slice(0, 10);
    const end = new Date(Date.now() + 86400000 * 22).toISOString().slice(0, 10);
    const reason = `HOD dedupe check ${tag}`;
    const payload = {
      leave_type: 'Casual Leave', coverage_officer: 'Maj. Cover',
      reason, start_date: start, end_date: end,
    };
    const first = await request.post('http://127.0.0.1:8000/leaves/', {
      headers: { Authorization: `Bearer ${token}` }, data: payload,
    });
    expect(first.status()).toBe(201);

    // A repeat submission is refused outright.
    const second = await request.post('http://127.0.0.1:8000/leaves/', {
      headers: { Authorization: `Bearer ${token}` }, data: payload,
    });
    expect(second.status()).toBe(400);

    await loginAs(page, 'hod');
    await page.waitForSelector('#nav-container .nav-btn');
    await page.click('.nav-btn:has-text("Leave Management")');
    await expect(page.locator(`tr:has-text("${reason}")`)).toHaveCount(1, { timeout: 15000 });
  });

  test('logout confirmation is an in-page dialog, not a native popup', async ({ page }) => {
    const dialogs: string[] = [];
    forbidNativeDialogs(page, dialogs);

    await loginAs(page, 'hod');
    await page.waitForSelector('.logout-btn');
    await page.click('.logout-btn');

    await expect(page.locator('.afid-dlg')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('.afid-dlg-head')).toContainText('Log Out');
    expect(dialogs).toEqual([]);
  });
});
