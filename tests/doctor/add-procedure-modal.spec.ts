import { test, expect } from '../fixtures/helpers';
import {
  loginAs, authHeaders, uniqueId, CREDS,
  DIALOG, acceptDialog, dismissDialog, dismissDialogIfOpen,
} from '../fixtures/helpers';

const API = 'http://localhost:8000';

// Grounded in a fresh read of doctor (1).html's openAddProcedureModal()
// against the CURRENT checkout:
//
//   async function openAddProcedureModal() {
//     const procName = await uiPrompt("Name of the procedure to add:", ...);
//     if (!procName || procName.trim() === "") return;
//     const durationInput = await uiPrompt("Approximate duration in minutes:", ...);
//     if (durationInput === null) return;
//     const duration = parseInt(durationInput, 10) || 30;
//     ...
//   }
//
// The two prompts are now the in-page `.afid-dlg` dialog from api.js rather
// than window.prompt(), so these tests drive DOM buttons via the shared
// acceptDialog()/dismissDialog() helpers instead of page.on('dialog').
// Native dialogs are prefixed by the browser with the page origin
// ("localhost:5173 says…"), which is exactly what that change removed.
//
// Otherwise unchanged: procedure presets come from the real backend
// (GET /presets/) merged over a built-in fallback catalogue, the dropdown
// append still guards on existingOptions.includes(cleanName) so no duplicate
// <option> is added, and `duration` is still parsed and stored on the
// in-memory preset object without any workspace UI ever reading it back out.

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
  await page.click('[data-page="operations"]');
  await page.fill('#patient-search-input', mrNumber);
  await page.click('text=Search & Continue');
  // Check-in feedback is now a toast, but an unexpected error would still
  // surface as an in-page dialog -- clear it rather than blocking on it.
  await page.waitForSelector('#view-workspace-screen.active', { timeout: 15000 });
  await dismissDialogIfOpen(page);
}

/**
 * Drives the two-step Add Procedure flow and returns the prompt text actually
 * shown, so tests can still assert which prompts appeared (and, crucially,
 * that the second one does NOT appear when the first is cancelled).
 */
async function addCustomProcedure(
  page: import('@playwright/test').Page,
  name: string | null,
  duration?: string
): Promise<string[]> {
  const seen: string[] = [];

  await page.click('button:has-text("Add Procedure")');
  await page.waitForSelector(DIALOG, { timeout: 10000 });
  seen.push((await page.locator(`${DIALOG} .afid-dlg-body`).innerText()).trim());

  if (name === null) {
    await dismissDialog(page);
  } else {
    await acceptDialog(page, name);
    // A blank/whitespace-only name short-circuits before the duration prompt.
    if (name.trim() !== '') {
      await page.waitForSelector(DIALOG, { timeout: 10000 });
      seen.push((await page.locator(`${DIALOG} .afid-dlg-body`).innerText()).trim());
      await acceptDialog(page, duration ?? '30');
    }
  }

  await page.waitForTimeout(200);
  return seen;
}

const NAME_PROMPT = 'Name of the procedure to add:';
const DURATION_PROMPT = 'Approximate duration in minutes:';

test('adding a brand-new custom procedure only fills the GLOBAL_MATERIALS baseline, with empty pharmacy/diagnostics and a generic auto-generated note', async ({ page, request }) => {
  await loginAs(page, 'doctor');
  const headers = await authHeaders(page);
  const patient = await seedPatient(request, headers);
  await openWorkspace(page, patient.mr_number);

  const procName = uniqueId('QA Custom Procedure');
  const seen = await addCustomProcedure(page, procName, '45');
  expect(seen).toEqual([NAME_PROMPT, DURATION_PROMPT]);

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

  expect(seen).toEqual([NAME_PROMPT]);
  await expect(page.locator('#procedure-select option')).toHaveCount(beforeCount);
});

test('a whitespace-only procedure name is treated exactly like cancelling -- procName.trim() === "" also short-circuits before the duration prompt', async ({ page, request }) => {
  await loginAs(page, 'doctor');
  const headers = await authHeaders(page);
  const patient = await seedPatient(request, headers);
  await openWorkspace(page, patient.mr_number);

  const beforeCount = await page.locator('#procedure-select option').count();
  const seen = await addCustomProcedure(page, '   ');

  expect(seen).toEqual([NAME_PROMPT]);
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
