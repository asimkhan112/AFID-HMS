import { test, expect } from '@playwright/test';
import { loginAs, authHeaders, uniqueId } from '../fixtures/helpers';

const API = 'http://localhost:8000';

// Grounded in a fresh read of doctor (1).html's buildAnalyticsRows() /
// processAndRenderDoctorAnalytics() against the CURRENT checkout. Both of
// the old scaffold's core findings here are fixed:
//
//   function buildAnalyticsRows() {
//     const currentName = getUser()?.full_name || LOGGED_IN_DOCTOR;
//     const myPatients = (cachedPatients || []).filter(patient => {
//       const assignedDoctor = patient.assigned_doctor || patient.doctor || '';
//       return assignedDoctor === currentName || assignedDoctor === LOGGED_IN_DOCTOR;
//     });
//     return myPatients.filter(patient => {
//       const status = (patient.status || '').toString().toUpperCase();
//       return status === 'ACTIVE' || status === 'COMPLETED';
//     }).map(...);
//   }
//
//   1. Rows are now genuinely filtered by `assigned_doctor` -- a patient
//      assigned to a different doctor no longer leaks into "My Analytics".
//   2. A still-WAITING patient (nothing ever completed) is now excluded
//      entirely, so it no longer inflates "Total Completed Procedures".
//
// What's unchanged: cachedPatients is still only ever fetched once, at
// login (loadDashboardData()'s Promise.all), so a patient registered after
// the doctor's session already loaded still never appears here. "Total
// Completed Procedures" also still literally reads rows.length, which now
// includes this doctor's ACTIVE (not just truly COMPLETED) patients -- a
// softer residual mislabeling, not the full-system leak the old scaffold
// found.

async function seedPatientAsRole(
  page: import('@playwright/test').Page,
  request: import('@playwright/test').APIRequestContext,
  role: 'receptionist' | 'doctor' | 'hod',
  opts: { assignedDoctor: string; procedureCategory: string; active?: boolean }
) {
  await loginAs(page, role);
  const headers = await authHeaders(page);
  const res = await request.post(`${API}/patients/`, {
    headers,
    data: {
      mr_number: uniqueId('QA-MR'),
      file_number: uniqueId('QA-F'),
      full_name: 'QA Analytics Patient',
      cnic: '66677-6667777-6',
      room: 'Room 10',
      assigned_doctor: opts.assignedDoctor,
      procedure_category: opts.procedureCategory,
    },
  });
  const patient = await res.json();
  if (opts.active) {
    await request.patch(`${API}/patients/${patient.id}/status`, { headers, data: { status: 'ACTIVE' } });
  }
  return patient;
}

test('"My Procedure History Log" no longer includes patients assigned to OTHER doctors -- buildAnalyticsRows() now genuinely filters by assigned_doctor', async ({ page, request }) => {
  const ownProc = uniqueId('QA-Own-Doctor-Procedure');
  const otherProc = uniqueId('QA-Other-Doctor-Procedure');
  await seedPatientAsRole(page, request, 'receptionist', { assignedDoctor: 'Dr. Rehan M.', procedureCategory: otherProc, active: true });
  await seedPatientAsRole(page, request, 'receptionist', { assignedDoctor: 'Dr. Asadullah Khan', procedureCategory: ownProc, active: true });

  await loginAs(page, 'doctor'); // Dr. Asadullah Khan
  await page.click('[data-page="doctor-analytics"]');

  const tbody = page.locator('#docAnalyticsTableBody');
  await expect(tbody).toContainText(ownProc);
  // The fix, as a positive assertion: a patient explicitly assigned to a
  // different doctor no longer shows up in "My" log.
  await expect(tbody).not.toContainText(otherProc);
});

test('a patient who is still WAITING (nothing ever completed) is correctly excluded from "My Procedure History Log" and does not inflate "Total Completed Procedures"', async ({ page, request }) => {
  const waitingProc = uniqueId('QA-Waiting-Never-Touched');
  await seedPatientAsRole(page, request, 'receptionist', { assignedDoctor: 'Dr. Asadullah Khan', procedureCategory: waitingProc });
  // Deliberately never PATCH this patient's status -- it stays WAITING.

  await loginAs(page, 'doctor');
  await page.click('[data-page="doctor-analytics"]');
  await expect(page.locator('#docAnalyticsTableBody')).not.toContainText(waitingProc);

  const personalCard = page.locator('#docAnalytics-personalCard');
  const beforeText = await personalCard.innerText();
  const totalBefore = Number(beforeText.match(/Total Completed Procedures:\s*(\d+)/)?.[1]);
  expect(Number.isFinite(totalBefore)).toBe(true);

  // Now add a genuinely ACTIVE patient for this doctor and reload the page
  // to pick up a fresh cachedPatients snapshot (loadDashboardData() only
  // runs on a full page load/reload, not on an in-app tab switch).
  const activeProc = uniqueId('QA-Active-For-Count');
  const headers = await authHeaders(page);
  const res = await request.post(`${API}/patients/`, {
    headers,
    data: {
      mr_number: uniqueId('QA-MR'),
      file_number: uniqueId('QA-F'),
      full_name: 'QA Analytics Patient',
      cnic: '66677-6667777-6',
      room: 'Room 10',
      assigned_doctor: 'Dr. Asadullah Khan',
      procedure_category: activeProc,
    },
  });
  const activePatient = await res.json();
  await request.patch(`${API}/patients/${activePatient.id}/status`, { headers, data: { status: 'ACTIVE' } });

  await page.reload();
  await page.click('[data-page="doctor-analytics"]');

  await expect(page.locator('#docAnalyticsTableBody')).toContainText(activeProc);
  await expect(page.locator('#docAnalyticsTableBody')).not.toContainText(waitingProc);

  const afterText = await personalCard.innerText();
  const totalAfter = Number(afterText.match(/Total Completed Procedures:\s*(\d+)/)?.[1]);
  // Exactly one new row counted -- the still-WAITING patient contributed nothing.
  expect(totalAfter).toBe(totalBefore + 1);
});

test('the "Duration" and "Difficulty Tier" columns are still derived purely from a keyword regex on the procedure_category text -- not any real recorded time', async ({ page, request }) => {
  const cases: Array<{ category: string; duration: string; tier: string }> = [
    { category: uniqueId('QA Root Canal Retreatment'), duration: '60 mins', tier: 'Complex (>50m)' },
    { category: uniqueId('QA Bracket Rebonding'), duration: '45 mins', tier: 'Moderate (25-50m)' },
    { category: uniqueId('QA Retainer Fit-Check'), duration: '30 mins', tier: 'Moderate (25-50m)' },
    { category: uniqueId('QA Initial Consultation Visit'), duration: '15 mins', tier: 'Easy (≤25m)' },
    { category: uniqueId('QA Unmatched Category Text'), duration: '25 mins', tier: 'Easy (≤25m)' },
  ];

  await loginAs(page, 'receptionist');
  const seedHeaders = await authHeaders(page);
  for (const c of cases) {
    const res = await request.post(`${API}/patients/`, {
      headers: seedHeaders,
      data: {
        mr_number: uniqueId('QA-MR'),
        file_number: uniqueId('QA-F'),
        full_name: 'QA Analytics Patient',
        cnic: '66677-6667777-6',
        room: 'Room 10',
        assigned_doctor: 'Dr. Asadullah Khan',
        procedure_category: c.category,
      },
    });
    const patient = await res.json();
    // These rows now need ACTIVE/COMPLETED status to show up at all
    // (buildAnalyticsRows() excludes WAITING patients).
    await request.patch(`${API}/patients/${patient.id}/status`, { headers: seedHeaders, data: { status: 'ACTIVE' } });
  }

  await loginAs(page, 'doctor');
  await page.click('[data-page="doctor-analytics"]');

  for (const c of cases) {
    const row = page.locator('#docAnalyticsTableBody tr', { hasText: c.category });
    await expect(row).toContainText(c.duration);
    await expect(row).toContainText(c.tier);
  }
});

test('the search box filters by keyword -- and, now that filterDoctorAnalytics() rebuilds rows through the same doctor-scoped buildAnalyticsRows(), only ever surfaces this doctor\'s own patients', async ({ page, request }) => {
  const otherProc = uniqueId('QA-Searchable-Other-Doctor');
  await seedPatientAsRole(page, request, 'receptionist', { assignedDoctor: 'Dr. Sana K.', procedureCategory: otherProc, active: true });

  await loginAs(page, 'doctor');
  await page.click('[data-page="doctor-analytics"]');
  await page.locator('#docAnalyticsSearch').pressSequentially(otherProc);

  await expect(page.locator('#docAnalyticsTableBody')).not.toContainText(otherProc);
  await expect(page.locator('#docAnalyticsTableBody tr')).toHaveCount(0);
});

test('a patient registered after the doctor\'s session already loaded never appears in "My Analytics" -- cachedPatients is still only ever fetched once, at login', async ({ page, request }) => {
  await loginAs(page, 'doctor');
  const headers = await authHeaders(page);

  const lateProc = uniqueId('QA-Registered-After-Login');
  const res = await request.post(`${API}/patients/`, {
    headers,
    data: {
      mr_number: uniqueId('QA-MR'),
      file_number: uniqueId('QA-F'),
      full_name: 'QA Late-Registered Patient',
      cnic: '55566-5556666-5',
      room: 'Room 10',
      assigned_doctor: 'Dr. Asadullah Khan',
      procedure_category: lateProc,
    },
  });
  const patient = await res.json();
  await request.patch(`${API}/patients/${patient.id}/status`, { headers, data: { status: 'ACTIVE' } });

  await page.click('[data-page="doctor-analytics"]');
  await expect(page.locator('#docAnalyticsTableBody')).not.toContainText(lateProc);
});
