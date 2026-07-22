import { test, expect } from '@playwright/test';
import { loginAs, authHeaders, uniqueId, fillPatientForm, rowFor } from '../fixtures/helpers';

const API = 'http://localhost:8000';

test.describe('Reception Patient Queue', () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page, 'receptionist');
    await page.click('[data-page="patient_mgmt"]');
  });

  test('registering a patient creates a visible WAITING row with correct doctor assignment', async ({ page, request }) => {
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
    // create_patient() in routers/patients.py stamps check_in_time immediately
    // at registration -- before the patient has actually been seen by anyone.
    // "Time In" on the table reflects this, so it's populated even for a
    // patient still sitting in the WAITING queue, not just ones a doctor has
    // actually started on.
    expect(patient.check_in_time).toBeTruthy();
    expect(patient.check_out_time).toBeNull();
    await expect(row).not.toContainText('— —'); // sanity: Time In column isn't blank
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

    // addPatient() only has a toast for errors -- there's no inline form
    // validation message, so this is the only signal the receptionist gets.
    await expect(page.locator('.toast').last()).toContainText(/already exists/i);

    // Confirm no second row was created and the original patient is untouched.
    await page.click('[data-page="patient_mgmt"]');
    await expect(rowFor(page, mr)).toHaveCount(1);
    await expect(rowFor(page, mr)).toContainText('QA Original Patient');
    await expect(rowFor(page, mr)).not.toContainText('QA Duplicate Attempt');
  });

  test('Doctor Management loads real allocations from API and allows creating new ones', async ({ page, request }) => {
    // The /allocations router is now registered in main.py, so the endpoint
    // should return 200 with an array (empty or populated).
    await loginAs(page, 'receptionist');

    const headers = await authHeaders(page);
    const getRes = await request.get(`${API}/allocations`, { headers });
    expect(getRes.status()).toBe(200);
    const allocations = await getRes.json();
    expect(Array.isArray(allocations)).toBe(true);

    await page.click('[data-page="doctor_mgmt"]');
    const table = page.locator('.panel', { hasText: 'Active Doctor Matrix' });
    
    // The table should show real doctors from the database, not just hardcoded fallbacks.
    // At least one seeded doctor should be visible if the database is seeded.
    const hasRealDoctors = await table.locator('tr').count() > 1; // header + at least one doctor
    expect(hasRealDoctors).toBe(true);

    // Test that we can create a new allocation via the UI.
    await page.fill('#d-name', 'Dr. QA New Hire');
    await page.locator('form:has(#d-name) button[type=submit]').click();

    // Should see a success toast, not a 404 error.
    await expect(page.locator('.toast').last()).toContainText(/allocation created/i);
    
    // The new doctor should appear in the table.
    await expect(table).toContainText('Dr. QA New Hire');

    // Verify via API that the allocation was actually created.
    const postRes = await request.get(`${API}/allocations`, { headers });
    const updatedAllocations = await postRes.json();
    const names = updatedAllocations.map((a: any) => a.doctor_name || a.name);
    expect(names).toContain('Dr. QA New Hire');
  });
});