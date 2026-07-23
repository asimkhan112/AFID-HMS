import { test, expect } from '@playwright/test';
import { loginAs, authHeaders, uniqueId } from '../fixtures/helpers';

const API = 'http://localhost:8000';

// Grounded in a fresh read of staff.html's selectTimelinePatient() and
// hod.html's hodSelectTimelinePatient() against the CURRENT checkout, plus
// routers/hod.py's add_timeline_step() (now behind
// require_role(hod, admin, doctor) -- a receptionist can no longer seed
// timeline steps directly, unlike the old scaffold's checkout, so seeding
// below is done via a doctor session instead).
//
// Two of the old scaffold's three findings here are fixed:
//
//   staff.html:
//     const inProgress = allSteps.filter(s => (s.status || '').toLowerCase() === 'in progress');
//   -- now compares against 'in progress' (a space), which correctly
//      matches StepStatus's real value "In Progress" lowercased. The old
//      'in_progress' (underscore) mismatch that silently dropped every
//      in-progress step from every bucket is gone.
//
//   hod.html: loadPortalData() now maps `name: step.step_name` when building
//   cachedTimelineSteps, and hodSelectTimelinePatient() renders
//   `${s.name || s.step_name || '—'}` -- so a completed step's real name
//   shows up correctly instead of the literal text "undefined".

async function seedPatientWithTimeline(
  page: import('@playwright/test').Page,
  request: import('@playwright/test').APIRequestContext
) {
  const headers = await authHeaders(page);
  const patientRes = await request.post(`${API}/patients/`, {
    headers,
    data: {
      mr_number: uniqueId('QA-MR'),
      file_number: uniqueId('QA-F'),
      full_name: 'QA Timeline Patient',
      cnic: '55555-5555555-5',
      room: 'Room 10',
      assigned_doctor: 'Dr. Asadullah Khan',
      procedure_category: 'Consultation',
    },
  });
  const patient = await patientRes.json();

  const stepNames = {
    pending: uniqueId('QA-Step-Pending'),
    inProgress: uniqueId('QA-Step-InProgress'),
    completed: uniqueId('QA-Step-Completed'),
  };

  await request.post(`${API}/hod/timeline/${encodeURIComponent(patient.mr_number)}/steps`, {
    headers,
    data: { step_order: 1, step_name: stepNames.pending, status: 'Pending' },
  });
  await request.post(`${API}/hod/timeline/${encodeURIComponent(patient.mr_number)}/steps`, {
    headers,
    data: { step_order: 2, step_name: stepNames.inProgress, status: 'In Progress' },
  });
  await request.post(`${API}/hod/timeline/${encodeURIComponent(patient.mr_number)}/steps`, {
    headers,
    data: { step_order: 3, step_name: stepNames.completed, status: 'Completed' },
  });

  return { patient, stepNames };
}

test('reception Patient Timeline: an "In Progress" step now correctly shows up in the in-progress list -- the old lowercase mismatch that silently dropped it is fixed', async ({ page, request }) => {
  // /hod/timeline/*/steps now requires hod/admin/doctor -- seed via a doctor
  // session, then switch to receptionist to check the reception-side view.
  await loginAs(page, 'doctor');
  const { patient, stepNames } = await seedPatientWithTimeline(page, request);

  await loginAs(page, 'receptionist');
  await page.click('[data-page="patient_timeline"]');
  await page.selectOption('#timeline-filter-type', 'mr');
  await page.fill('#timeline-search-input', patient.mr_number);
  await page.click('text=Search');
  await page.click(`text=${patient.mr_number}`);

  const stepsList = page.locator('#timeline-steps-list');
  await expect(page.locator('#timeline-total-badge')).toHaveText('Total Performed: 1');
  await expect(stepsList).toContainText(stepNames.pending);
  await expect(stepsList).toContainText(stepNames.completed);
  // The fix, as a positive assertion: the in-progress step is genuinely
  // visible now, not silently dropped from every bucket.
  await expect(stepsList).toContainText(stepNames.inProgress);

  // Confirm it's the same three steps on the backend too.
  const headers = await authHeaders(page);
  const res = await request.get(`${API}/hod/timeline/${encodeURIComponent(patient.mr_number)}`, { headers });
  const allSteps = await res.json();
  expect(allSteps).toHaveLength(3);
  expect(allSteps.some((s: any) => s.step_name === stepNames.inProgress && s.status === 'In Progress')).toBe(true);
});

test('HOD Patient Timeline: completed procedure names now render correctly -- the old literal "undefined" bug is fixed', async ({ page, request }) => {
  await loginAs(page, 'doctor');
  const { patient, stepNames } = await seedPatientWithTimeline(page, request);

  await loginAs(page, 'hod');
  await page.click('text=Patient Timeline');
  await page.selectOption('#hod-timeline-filter-type', 'mr_number');
  await page.fill('#hod-timeline-search-input', patient.mr_number);
  await page.click('text=Search');
  await page.click(`text=${patient.mr_number}`);

  await expect(page.locator('#hod-timeline-total-badge')).toHaveText('Total Performed: 1');
  const stepsList = page.locator('#hod-timeline-steps-list');
  await expect(stepsList).toContainText(stepNames.completed);
  await expect(stepsList).not.toContainText('undefined');
});

test('reception Patient Timeline: a patient with no timeline steps shows an empty state instead of an error', async ({ page, request }) => {
  await loginAs(page, 'receptionist');
  const headers = await authHeaders(page);
  const res = await request.post(`${API}/patients/`, {
    headers,
    data: {
      mr_number: uniqueId('QA-MR'),
      file_number: uniqueId('QA-F'),
      full_name: 'QA No-Timeline Patient',
      cnic: '66666-6666666-6',
      room: 'Room 11',
      assigned_doctor: 'Dr. Rehan M.',
      procedure_category: 'Consultation',
    },
  });
  const patient = await res.json();

  await page.click('[data-page="patient_timeline"]');
  await page.fill('#timeline-search-input', patient.mr_number);
  await page.click('text=Search');
  await page.click(`text=${patient.mr_number}`);

  await expect(page.locator('#timeline-total-badge')).toHaveText('Total Performed: 0');
  await expect(page.locator('#timeline-steps-list')).toContainText('No pending steps');
  await expect(page.locator('#timeline-steps-list')).toContainText('No in-progress steps');
  await expect(page.locator('#timeline-steps-list')).toContainText('No completed procedures yet');
});
