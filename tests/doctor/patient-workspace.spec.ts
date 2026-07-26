import { test, expect } from '../fixtures/helpers';
import { DIALOG, acceptDialog, dialogText, dismissDialogIfOpen } from '../fixtures/helpers';
import { loginAs, authHeaders, uniqueId, CREDS } from '../fixtures/helpers';

const API = 'http://localhost:8000';

async function seedPatient(
  request: import('@playwright/test').APIRequestContext,
  headers: Record<string, string>,
  opts: Partial<{ allergies: string; assignedDoctor: string }> = {}
) {
  const mr = uniqueId('QA-MR');
  const res = await request.post(`${API}/patients/`, {
    headers,
    data: {
      mr_number: mr,
      file_number: uniqueId('QA-F'),
      full_name: 'QA Doctor-Portal Patient',
      cnic: '99999-9999999-9',
      gender: 'Male',
      blood_group: 'O+',
      service_profile: 'Major',
      allergies: opts.allergies ?? '',
      room: 'Room 10',
      assigned_doctor: opts.assignedDoctor ?? 'Dr. Asadullah Khan',
      procedure_category: 'Consultation',
    },
  });
  return res.json();
}

test('searching for a WAITING patient auto-checks them in and populates the workspace profile', async ({ page, request }) => {
  await loginAs(page, 'doctor');
  const headers = await authHeaders(page);
  const patient = await seedPatient(request, headers);

  // executeSearch() auto-transitions a WAITING patient to ACTIVE and reports
  // the check-in time in a non-blocking in-page toast. It used to be a native
  // alert(), which the browser prefixes with the page origin; nothing should
  // fire a native dialog here any more.
  let nativeDialogFired = false;
  page.on('dialog', async (dialog) => { nativeDialogFired = true; await dialog.dismiss(); });

  await page.click('[data-page="operations"]');
  await page.fill('#patient-search-input', patient.mr_number);
  await page.click('text=Search & Continue');

  await expect(page.locator('#view-workspace-screen')).toHaveClass(/active/);
  await expect(page.locator('body')).toContainText(/checked in at/i, { timeout: 10000 });
  expect(nativeDialogFired).toBe(false);

  await expect(page.locator('#active-patient-badge')).toContainText(patient.mr_number);
  const values = page.locator('#view-workspace-screen .patient-details-grid .value');
  await expect(values.nth(0)).toHaveText('QA Doctor-Portal Patient');
  await expect(values.nth(1)).toContainText(patient.mr_number);
  // The profile now reports the patient's real case status. The "Open Case"
  // badge alone used to be the closest thing to a status readout, which made
  // an already-completed case look as though it were still in progress.
  await expect(values.nth(5)).toHaveText('ACTIVE');

  // Time In should no longer be blank now that the auto-check-in has fired.
  await expect(page.locator('#patient-time-in')).not.toHaveValue('—');
  await expect(page.locator('#patient-time-in')).not.toHaveValue('');

  const res = await request.get(`${API}/patients/lookup/mr/${encodeURIComponent(patient.mr_number)}`, { headers });
  const updated = await res.json();
  expect(updated.status).toBe('ACTIVE');
  expect(updated.check_in_time).toBeTruthy();
});

test('an allergy on the patient record shows a critical allergy banner; a patient with none shows no banner', async ({ page, request }) => {
  await loginAs(page, 'doctor');
  const headers = await authHeaders(page);


  const allergicPatient = await seedPatient(request, headers, { allergies: 'Penicillin Sensitivity' });
  await page.click('[data-page="operations"]');
  await page.fill('#patient-search-input', allergicPatient.mr_number);
  await page.click('text=Search & Continue');
  await expect(page.locator('#allergy-alert-box')).toBeVisible();
  await expect(page.locator('#allergy-alert-box')).toContainText('Penicillin Sensitivity');

  await page.click('text=Back to Search Lookup');
  const cleanPatient = await seedPatient(request, headers, { allergies: '' });
  await page.fill('#patient-search-input', cleanPatient.mr_number);
  await page.click('text=Search & Continue');
  await expect(page.locator('#allergy-alert-box')).toBeHidden();
});

test('applying a backend-seeded procedure preset auto-fills materials, pharmacy, diagnostics, and notes for that procedure', async ({ page, request }) => {
  // Procedure presets are now a real backend feature (GET/POST /presets/,
  // the new procedure_presets tables) rather than a hardcoded client-side
  // object, and cachedPresets is a load-once snapshot taken at login -- so
  // the preset used here is seeded via the API BEFORE the doctor's browser
  // session logs in, guaranteeing it's present regardless of whether
  // seed_presets.py has already been run against this checkout's database.
  const apiLoginRes = await request.post(`${API}/auth/login`, {
    data: { email: CREDS.doctor.email, password: CREDS.doctor.password },
  });
  const { access_token } = await apiLoginRes.json();
  const apiHeaders = { Authorization: `Bearer ${access_token}` };

  const presetName = uniqueId('QA Root Canal Preset');
  await request.post(`${API}/presets/`, {
    headers: apiHeaders,
    data: {
      name: presetName,
      duration: 60,
      notes: 'QA root canal access cavity established under rubber dam isolation.',
      materials: [
        { name: 'Gutta-Percha Points (ISO 30)', quantity: 6 },
        { name: 'AH Plus Sealer (1.5g)', quantity: 1 },
      ],
      pharmacy: [
        { medication: 'Amoxicillin 500mg', dose: '500mg', frequency: 'TDS x 5 days' },
        { medication: 'Ibuprofen 400mg', dose: '400mg', frequency: 'BD PRN pain' },
      ],
      diagnostics: [
        { test_name: 'CBCT', urgency: 'Routine' },
        { test_name: 'Full Mouth Periapical X-rays', urgency: 'Routine' },
      ],
    },
  });
  const patient = await seedPatient(request, apiHeaders);

  await loginAs(page, 'doctor');
  await page.click('[data-page="operations"]');
  await page.fill('#patient-search-input', patient.mr_number);
  await page.click('text=Search & Continue');

  await page.selectOption('#procedure-select', presetName);

  // Materials list includes both the procedure-specific items and the
  // GLOBAL_MATERIALS baseline that's prepended for every procedure.
  const materials = page.locator('#materials-log-list');
  await expect(materials).toContainText('Gutta-Percha Points (ISO 30)');
  await expect(materials).toContainText('AH Plus Sealer (1.5g)');
  await expect(materials).toContainText('Napkin'); // GLOBAL_MATERIALS baseline
  await expect(materials).toContainText('Sterilization pouch');

  const pharmacy = page.locator('#pharmacy-log-list');
  await expect(pharmacy).toContainText('Amoxicillin 500mg');
  await expect(pharmacy).toContainText('Ibuprofen 400mg');

  const diagnostics = page.locator('#diagnostics-list');
  await expect(diagnostics).toContainText('CBCT');
  await expect(diagnostics).toContainText('Full Mouth Periapical X-rays');

  await expect(page.locator('#clinical-notes-textarea')).toHaveValue(/QA root canal access cavity established/);
});

test('completing a session now genuinely persists everything entered -- the procedure session, materials, pharmacy, diagnostics, and notes are all saved to the backend, fixing the old "nothing is saved" gap', async ({ page, request }) => {
  // confirmTimeOut() now runs a real sequence of POST /procedures/, then
  // POST .../materials, .../pharmacy, .../diagnostics, .../notes for
  // everything currently in the workspace, before PATCHing the patient to
  // COMPLETED -- its confirm() dialog's "This will save the session
  // summary" wording is accurate now, where before it was misleading.
  const apiLoginRes = await request.post(`${API}/auth/login`, {
    data: { email: CREDS.doctor.email, password: CREDS.doctor.password },
  });
  const { access_token } = await apiLoginRes.json();
  const apiHeaders = { Authorization: `Bearer ${access_token}` };

  const presetName = uniqueId('QA Persisted Preset');
  await request.post(`${API}/presets/`, {
    headers: apiHeaders,
    data: {
      name: presetName,
      duration: 60,
      notes: 'QA persisted procedure notes.',
      materials: [{ name: 'QA Persisted Material', quantity: 2 }],
      pharmacy: [{ medication: 'QA Persisted Med', dose: '1 tab', frequency: 'OD' }],
      diagnostics: [{ test_name: 'QA Persisted Diagnostic', urgency: 'Routine' }],
    },
  });
  const patient = await seedPatient(request, apiHeaders);

  await loginAs(page, 'doctor');
  const headers = await authHeaders(page);

  let nativeDialogFired = false;
  page.on('dialog', async (dialog) => { nativeDialogFired = true; await dialog.dismiss(); });

  await page.click('[data-page="operations"]');
  await page.fill('#patient-search-input', patient.mr_number);
  await page.click('text=Search & Continue');
  await expect(page.locator('#view-workspace-screen')).toHaveClass(/active/);
  await page.selectOption('#procedure-select', presetName);
  await expect(page.locator('#materials-log-list')).toContainText('QA Persisted Material');

  await page.click('text=Confirm Time & Complete Session');

  // The confirmation is the in-page dialog, and it now itemises exactly what
  // is about to be saved rather than making a vague promise.
  await expect(page.locator(DIALOG)).toBeVisible({ timeout: 10000 });
  const confirmText = await dialogText(page);
  expect(confirmText).toContain('Complete the session for');
  expect(confirmText).toContain(presetName);
  expect(confirmText).toMatch(/Materials: \d+/);
  await acceptDialog(page);

  // Accepting the dialog kicks off a real chain of sequential
  // POST /procedures/, then .../materials, .../pharmacy, .../diagnostics,
  // .../notes, a timeline step, and finally a PATCH to COMPLETED. Wait for the
  // observable end state rather than racing the network calls.
  await expect(page.locator('body')).toContainText(/session completed and saved successfully/i, { timeout: 15000 });
  expect(nativeDialogFired).toBe(false);

  await expect(page.locator('#patient-time-out')).not.toHaveValue('—');

  // The summary sheet is rendered BEFORE the working set is cleared, so
  // everything that was just saved actually appears on it. It used to be
  // compiled after the arrays were emptied, so a completed session always
  // printed "No clinical components allocated" and no medications.
  const summary = page.locator('#master-summary-injection-point');
  await expect(summary).toContainText('QA Persisted Material');
  await expect(summary).toContainText('QA Persisted Med');
  await expect(summary).toContainText('QA Persisted Diagnostic');
  // …attributed to the doctor who is actually signed in.
  await expect(summary).toContainText('Dr. Asadullah Khan');

  const statusRes = await request.get(`${API}/patients/lookup/mr/${encodeURIComponent(patient.mr_number)}`, { headers });
  const completed = await statusRes.json();
  expect(completed.status).toBe('COMPLETED');
  expect(completed.check_out_time).toBeTruthy();

  // The fix, as a positive assertion: the procedure session and everything
  // logged in it really did reach the backend this time.
  const procRes = await request.get(`${API}/patients/${completed.id}/procedures`, { headers });
  const withProcedures = await procRes.json();
  expect(withProcedures.procedures.length).toBeGreaterThan(0);
  const savedProc = withProcedures.procedures.find((p: any) => p.name === presetName);
  expect(savedProc).toBeTruthy();
  expect(savedProc.materials_count).toBeGreaterThan(0);
  expect(savedProc.pharmacy_count).toBeGreaterThan(0);
  expect(savedProc.diagnostics_count).toBeGreaterThan(0);
  expect(savedProc.notes_count).toBeGreaterThan(0);
});
