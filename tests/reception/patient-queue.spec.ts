import { test, expect } from '../fixtures/helpers';
import { DIALOG, dialogText, acceptDialog } from '../fixtures/helpers';
import { loginAs, authHeaders, uniqueId, fillPatientForm, rowFor } from '../fixtures/helpers';

const API = 'http://localhost:8000';

test.describe('Reception Patient Queue', () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page, 'receptionist');
    await page.click('[data-page="patient_mgmt"]');
  });

  test('registering a patient creates a visible WAITING row with correct doctor assignment', async ({ page, request }) => {
    await page.click('[data-page="patient_reg"]');

    const mr = uniqueId('QA-MR');
    const file = uniqueId('QA-F');
    await fillPatientForm(page, { mr, file, name: 'QA Patient One', cnic: '11111-1111111-1', doctor: 'Dr. Rehan M.' });
    await page.click('#patient-form button[type=submit]');

    const row = rowFor(page, mr);
    await expect(row).toBeVisible();
    await expect(row.locator('.badge')).toHaveText('WAITING');
    await expect(row).toContainText('Dr. Rehan M.');
    // "Start" should still be offered since the patient hasn't been seen yet.
    await expect(row.locator('button', { hasText: 'Start' })).toBeVisible();

    const headers = await authHeaders(page);
    const res = await request.get(`${API}/patients/lookup/mr/${encodeURIComponent(mr)}`, { headers });
    const patient = await res.json();
    expect(patient.status).toBe('WAITING');
    // create_patient() never touches check_in_time -- it's only stamped in
    // update_status() when the patient transitions to ACTIVE (see "Start"
    // below). A freshly-registered WAITING patient correctly has no check-in
    // yet; this is the deferred-check-in behavior the QA findings guide
    // noted as already fixed relative to an earlier copy of this app.
    expect(patient.check_in_time).toBeNull();
    expect(patient.check_out_time).toBeNull();
  });

  test('Start then Complete moves a patient from WAITING to ACTIVE to COMPLETED and stamps check-out', async ({ page, request }) => {
    await page.click('[data-page="patient_reg"]');

    const mr = uniqueId('QA-MR');
    const file = uniqueId('QA-F');
    await fillPatientForm(page, { mr, file, name: 'QA Patient Lifecycle', cnic: '22222-2222222-2' });
    await page.click('#patient-form button[type=submit]');

    const row = rowFor(page, mr);
    await expect(row.locator('.badge')).toHaveText('WAITING');

    await row.locator('button', { hasText: 'Start' }).click();
    await expect(page.locator('.toast').last()).toContainText('Time In recorded');
    await expect(rowFor(page, mr).locator('.badge')).toHaveText('ACTIVE');
    await expect(rowFor(page, mr).locator('button', { hasText: 'Complete' })).toBeVisible();

    const headers = await authHeaders(page);
    let res = await request.get(`${API}/patients/lookup/mr/${encodeURIComponent(mr)}`, { headers });
    let patient = await res.json();
    expect(patient.status).toBe('ACTIVE');
    expect(patient.check_out_time).toBeNull();

    await rowFor(page, mr).locator('button', { hasText: 'Complete' }).click();
    await expect(page.locator('.toast').last()).toContainText('Time Out recorded');
    await expect(rowFor(page, mr).locator('.badge')).toHaveText('COMPLETED');
    // Terminal state -- no more action buttons, just "Done".
    await expect(rowFor(page, mr)).toContainText('Done');

    res = await request.get(`${API}/patients/lookup/mr/${encodeURIComponent(mr)}`, { headers });
    patient = await res.json();
    expect(patient.status).toBe('COMPLETED');
    expect(patient.check_out_time).toBeTruthy();
  });

  test('registering a patient with a duplicate MR number is rejected, and no duplicate row is created', async ({ page, request }) => {
    await page.click('[data-page="patient_reg"]');

    const mr = uniqueId('QA-MR');
    await fillPatientForm(page, { mr, file: uniqueId('QA-F'), name: 'QA Original Patient', cnic: '33333-3333333-3' });
    await page.click('#patient-form button[type=submit]');
    await expect(rowFor(page, mr)).toContainText('QA Original Patient');

    // Re-register with the exact same MR number but different everything else.
    await page.click('[data-page="patient_reg"]');
    await fillPatientForm(page, { mr, file: uniqueId('QA-F'), name: 'QA Duplicate Attempt', cnic: '44444-4444444-4' });
    await page.click('#patient-form button[type=submit]');

    // A rejected registration now surfaces in the in-page dialog rather than a
    // transient toast, so the receptionist cannot miss it. (Native alert() is
    // not used anywhere -- the browser prefixes those with the page origin.)
    await expect(page.locator(DIALOG)).toBeVisible({ timeout: 10000 });
    expect(await dialogText(page)).toMatch(/already exists/i);
    await acceptDialog(page);

    // Confirm no second row was created and the original patient is untouched.
    await page.click('[data-page="patient_mgmt"]');
    await expect(rowFor(page, mr)).toHaveCount(1);
    await expect(rowFor(page, mr)).toContainText('QA Original Patient');
    await expect(rowFor(page, mr)).not.toContainText('QA Duplicate Attempt');
  });

  test('Doctor Management loads real allocations from API and allocates a registered doctor to a room', async ({ page, request }) => {
    const headers = await authHeaders(page);
    const getRes = await request.get(`${API}/allocations`, { headers });
    expect(getRes.status()).toBe(200);
    expect(Array.isArray(await getRes.json())).toBe(true);

    // "Doctor Name" is a picker over real doctor ACCOUNTS, not a free-text
    // box. Patients are linked to a doctor by name, and the doctor portal
    // matches its queue on the signed-in user's full_name -- a typed-in name
    // with no account behind it produced allocations for a "doctor" who could
    // never log in and never see the patients assigned to them.
    const doctorName = uniqueId('Dr. QA New Hire');
    const regRes = await request.post(`${API}/auth/register`, {
      headers,
      data: { full_name: doctorName, email: `${uniqueId('qa.hire')}@afid.mil`, password: 'doctor1234', role: 'doctor' },
    });
    expect(regRes.status()).toBe(201);

    // Free a room to allocate into, so a full ward can't fail this test.
    const room = 'Room 13';
    for (const a of await (await request.get(`${API}/allocations`, { headers })).json()) {
      if (a.room === room) await request.delete(`${API}/allocations/${a.id}`, { headers });
    }

    await page.click('[data-page="doctor_mgmt"]');
    const table = page.locator('.panel', { hasText: 'Active Doctor Matrix' });
    await expect(table).toContainText(doctorName, { timeout: 15000 });

    await page.selectOption('#d-name', doctorName);
    await page.selectOption('#d-room', room);
    await page.locator('#doctor-form button[type=submit]').click();

    await expect(page.locator('.toast').last()).toContainText(new RegExp(`allocated to ${room}`, 'i'));
    await expect(table.locator('tr', { hasText: doctorName })).toContainText(room);

    // Verify via API that the allocation was actually created.
    const postRes = await request.get(`${API}/allocations`, { headers });
    const updatedAllocations = await postRes.json();
    const match = updatedAllocations.filter((a: any) => a.doctor_name === doctorName);
    // Exactly one row -- allocation is an upsert keyed on the doctor, so a
    // doctor can never end up occupying two rooms at once.
    expect(match).toHaveLength(1);
    expect(match[0].room).toBe(room);
  });
});