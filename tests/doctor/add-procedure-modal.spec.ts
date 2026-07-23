import { test, expect } from '@playwright/test';
import { loginAs, authHeaders, uniqueId, CREDS } from '../fixtures/helpers';

const API = 'http://localhost:8000';

// Grounded in a fresh read of doctor (1).html's openAddProcedureModal()
// against the CURRENT checkout:
//
//   function openAddProcedureModal() {
//     const procName = prompt("Enter new procedure name:");
//     if (!procName || procName.trim() === "") return;
//     const duration = parseInt(prompt("Enter procedure duration (minutes):")) || 30;
//     const cleanName = procName.trim();
//     if (!cachedPresets[cleanName]) {
//       cachedPresets[cleanName] = { materials: [], pharmacy: [], diagnostics: [],
//                                     notes: `Procedure performed: ${cleanName}.`, duration };
//     }
//     const select = document.getElementById('procedure-select');
//     const existingOptions = Array.from(select.options).map(opt => opt.value);
//     if (!existingOptions.includes(cleanName)) {
//       const newOption = document.createElement('option');
//       newOption.value = cleanName; newOption.text = cleanName;
//       select.appendChild(newOption);
//     }
//     select.value = cleanName;
//     applyProcedure();
//   }
//
// Two things changed from the old scaffold's checkout: procedure presets are
// now loaded from the real backend (GET /presets/, the new procedure_presets
// feature) into `cachedPresets` instead of a hardcoded JS object, and the
// dropdown append now DOES check `existingOptions.includes(cleanName)`
// before appending -- so the old "duplicate <option> on every call" bug is
// fixed. `duration` is still parsed from the second prompt and stored on the
// in-memory preset object, but nothing in the workspace UI ever reads
// data.duration back out -- that part of the old finding still holds.
//
// Because presets now come from the backend and cachedPresets is a
// load-once snapshot taken at login, "an existing preset" is seeded here via
// POST /presets/ with a unique name (logged in via the API before the
// browser session logs in) rather than assumed to already exist under a
// fixed curated name -- this doesn't depend on whether seed_presets.py has
// been run against this checkout's database.

async function seedPatient(request: import('@playwright/test').APIRequestContext, headers: Record<string, string>) {
  const res = await request.post(`${API}/patients/`, {
    headers,
    data: {
      mr_number: uniqueId('QA-MR'),
      file_number: uniqueId('QA-F'),
      full_name: 'QA Add-Procedure Patient',
      cnic: '88888-8888888-8',
      room: 'Room 10',
      assigned_doctor: 'Dr. Asadullah Khan',
      procedure_category: 'Consultation',
    },
  });
  return res.json();
}

async function seedPreset(
  request: import('@playwright/test').APIRequestContext,
  headers: Record<string, string>,
  name: string
) {
  const res = await request.post(`${API}/presets/`, {
    headers,
    data: {
      name,
      duration: 15,
      notes: `QA seeded notes for ${name}.`,
      materials: [{ name: 'QA Seeded Material', quantity: 1 }],
      pharmacy: [],
      diagnostics: [],
    },
  });
  return res.json();
}

async function openWorkspace(page: import('@playwright/test').Page, mrNumber: string) {
  const acceptAll = (dialog: import('@playwright/test').Dialog) => dialog.accept();
  page.on('dialog', acceptAll);
  await page.click('[data-page="operations"]');
  await page.fill('#patient-search-input', mrNumber);
  await page.click('text=Search & Continue');
  await page.waitForTimeout(200);
  page.off('dialog', acceptAll);
}

async function addCustomProcedure(
  page: import('@playwright/test').Page,
  name: string | null,
  duration?: string
): Promise<string[]> {
  const seen: string[] = [];
  const handler = async (dialog: import('@playwright/test').Dialog) => {
    seen.push(dialog.message());
    if (dialog.message().startsWith('Enter new procedure name')) {
      if (name === null) await dialog.dismiss();
      else await dialog.accept(name);
    } else if (dialog.message().startsWith('Enter procedure duration')) {
      await dialog.accept(duration ?? '30');
    } else {
      await dialog.accept();
    }
  };
  page.on('dialog', handler);
  await page.click('button:has-text("Add Procedure")');
  await page.waitForTimeout(300);
  page.off('dialog', handler);
  return seen;
}

test('adding a brand-new custom procedure only fills the GLOBAL_MATERIALS baseline, with empty pharmacy/diagnostics and a generic auto-generated note', async ({ page, request }) => {
  await loginAs(page, 'doctor');
  const headers = await authHeaders(page);
  const patient = await seedPatient(request, headers);
  await openWorkspace(page, patient.mr_number);

  const procName = uniqueId('QA Custom Procedure');
  const seen = await addCustomProcedure(page, procName, '45');
  expect(seen).toEqual(['Enter new procedure name:', 'Enter procedure duration (minutes):']);

  await expect(page.locator('#procedure-select')).toHaveValue(procName);
  await expect(page.locator(`#procedure-select option[value="${procName}"]`)).toHaveCount(1);

  const materials = page.locator('#materials-log-list');
  await expect(materials).toContainText('Napkin');
  await expect(materials).toContainText('Sterilization pouch');
  await expect(materials).toContainText('Suction tip');

  await expect(page.locator('#pharmacy-log-list')).toContainText('No medications logged.');
  await expect(page.locator('#diagnostics-list')).toContainText('No diagnostics requested.');
  await expect(page.locator('#clinical-notes-textarea')).toHaveValue(`Procedure performed: ${procName}.`);
});

test('cancelling the procedure-name prompt aborts the whole flow -- the duration prompt never even appears, and nothing is added', async ({ page, request }) => {
  await loginAs(page, 'doctor');
  const headers = await authHeaders(page);
  const patient = await seedPatient(request, headers);
  await openWorkspace(page, patient.mr_number);

  const beforeCount = await page.locator('#procedure-select option').count();
  const seen = await addCustomProcedure(page, null);

  expect(seen).toEqual(['Enter new procedure name:']);
  await expect(page.locator('#procedure-select option')).toHaveCount(beforeCount);
});

test('a whitespace-only procedure name is treated exactly like cancelling -- procName.trim() === "" also short-circuits before the duration prompt', async ({ page, request }) => {
  await loginAs(page, 'doctor');
  const headers = await authHeaders(page);
  const patient = await seedPatient(request, headers);
  await openWorkspace(page, patient.mr_number);

  const beforeCount = await page.locator('#procedure-select option').count();
  const seen = await addCustomProcedure(page, '   ');

  expect(seen).toEqual(['Enter new procedure name:']);
  await expect(page.locator('#procedure-select option')).toHaveCount(beforeCount);
});

test('clicking "+ Add Procedure" twice with the identical name no longer adds a duplicate dropdown entry -- the old duplicate-option bug is fixed', async ({ page, request }) => {
  await loginAs(page, 'doctor');
  const headers = await authHeaders(page);
  const patient = await seedPatient(request, headers);
  await openWorkspace(page, patient.mr_number);

  const procName = uniqueId('QA Repeated Procedure');
  await addCustomProcedure(page, procName, '20');
  await expect(page.locator(`#procedure-select option[value="${procName}"]`)).toHaveCount(1);

  await addCustomProcedure(page, procName, '99');
  // existingOptions.includes(cleanName) now guards the append -- still 1.
  await expect(page.locator(`#procedure-select option[value="${procName}"]`)).toHaveCount(1);
});

test('typing the name of an existing backend-seeded preset does not corrupt its real materials, and no longer adds a duplicate dropdown entry either', async ({ page, request }) => {
  // Presets are cached once at login -- seed via a direct API login BEFORE
  // the browser session logs in, so it's already present in this doctor's
  // cachedPresets snapshot once the page loads.
  const apiLoginRes = await request.post(`${API}/auth/login`, {
    data: { email: CREDS.doctor.email, password: CREDS.doctor.password },
  });
  const { access_token } = await apiLoginRes.json();
  const apiHeaders = { Authorization: `Bearer ${access_token}` };

  const presetName = uniqueId('QA Existing Preset');
  await seedPreset(request, apiHeaders, presetName);
  const patient = await seedPatient(request, apiHeaders);

  await loginAs(page, 'doctor');
  await openWorkspace(page, patient.mr_number);

  await expect(page.locator(`#procedure-select option[value="${presetName}"]`)).toHaveCount(1);

  await addCustomProcedure(page, presetName, '15');

  // Still exactly one option -- no duplicate appended.
  await expect(page.locator(`#procedure-select option[value="${presetName}"]`)).toHaveCount(1);

  // And the real seeded materials/notes are untouched -- the
  // `if (!cachedPresets[cleanName])` guard did its job, same as before.
  await page.selectOption('#procedure-select', presetName);
  await expect(page.locator('#materials-log-list')).toContainText('QA Seeded Material');
  await expect(page.locator('#clinical-notes-textarea')).toHaveValue(`QA seeded notes for ${presetName}.`);
});

test('the procedure duration entered in the second prompt is collected and then discarded -- it never appears anywhere in the resulting workspace UI', async ({ page, request }) => {
  await loginAs(page, 'doctor');
  const headers = await authHeaders(page);
  const patient = await seedPatient(request, headers);
  await openWorkspace(page, patient.mr_number);

  const procName = uniqueId('QA Duration Procedure');
  const distinctiveDuration = '7373'; // unlikely to collide with any real page text
  await addCustomProcedure(page, procName, distinctiveDuration);

  await expect(page.locator('#procedure-select')).toHaveValue(procName);
  await expect(page.locator('#view-workspace-screen')).not.toContainText(distinctiveDuration);
});
