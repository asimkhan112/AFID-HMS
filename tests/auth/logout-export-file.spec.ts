import * as fs from 'fs';
import * as path from 'path';
import * as XLSX from 'xlsx';
import { test, expect } from '../fixtures/helpers';
import { CREDS, uniqueId } from '../fixtures/helpers';

const API = 'http://localhost:8000';
const DOCTOR_NAME = 'Dr. Asadullah Khan';

// Grounded in a fresh read of AFID backend/excel_exporter.py against the
// CURRENT checkout. Its generate_queue_excel() now is:
//
//   filename = f"{sanitized_doctor_name}_{now.strftime('%Y-%m-%d_%H-%M-%S')}.xlsx"
//   headers = ["Queue Number", "Patient ID", "Patient Name", "Age", "Gender",
//              "Visit Date", "Visit Time", "Status", "Doctor Name"]
//   ... one row per patient dict, Age always "N/A" ...
//
// The filename now includes SECONDS, not just minutes -- this fixes the old
// scaffold's finding that two logouts within the same clock minute silently
// clobber each other. The third test below is rewritten to prove that fix:
// two logouts spaced more than a second apart now each get their own file.
//
// These tests read the .xlsx file the backend process writes to its own
// local disk directly, using Node's `fs` and the `xlsx` package (already an
// existing devDependency of this project, per package.json) -- both run in
// the same Node process executing this test file, on the same machine as
// the backend. playwright.config.ts's own webServer entries run from this
// project's root with `cwd: './AFID backend'`, and this test file's process
// (playwright itself) also runs from that same root -- so process.cwd()
// here already IS the project root; the exports folder is one level down at
// 'AFID backend/exports', not up-and-over like a separate sibling QA folder
// would need.

function exportsDir(): string {
  return path.resolve(process.cwd(), 'AFID backend', 'exports');
}

function listExportFiles(): string[] {
  const dir = exportsDir();
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir);
}

// The backend process writes the export file to disk asynchronously from
// this Node test process's point of view -- POST /auth/logout can return
// export_status: "exported:N" (proving the write happened) a moment before
// this process's fs.readdirSync() actually observes the new file. A single
// immediate check occasionally raced this and saw zero new files even
// though the export genuinely succeeded. Poll instead of checking once.
async function waitForNewExportFile(before: Set<string>): Promise<string[]> {
  let found: string[] = [];
  await expect.poll(() => {
    found = listExportFiles().filter((f) => !before.has(f));
    return found.length;
  }, { timeout: 10000 }).toBeGreaterThan(0);
  return found;
}

async function loginAsDoctorViaApi(request: import('@playwright/test').APIRequestContext) {
  const res = await request.post(`${API}/auth/login`, {
    data: { email: CREDS.doctor.email, password: CREDS.doctor.password },
  });
  const { access_token } = await res.json();
  return { Authorization: `Bearer ${access_token}` };
}

// NOTE: this file used to hand-track every patient ID it seeded and
// complete them in its own afterEach, because POST /auth/logout only ever
// *exports* the WAITING/ACTIVE queue -- it never changes patient status --
// so without cleanup, patients seeded here stayed ACTIVE in the shared dev
// database and inflated counts/queues in other spec files that ran later in
// the same suite (e.g. tests/doctor/my-analytics.spec.ts,
// tests/auth/logout-export.spec.ts). That per-file tracking is now
// superseded by the suite-wide auto-cleanup fixture in
// tests/fixtures/helpers.ts, which sweeps every still-WAITING/ACTIVE
// QA-prefixed patient after every test in every spec file automatically --
// no local tracking needed here anymore.
async function seedPatient(
  request: import('@playwright/test').APIRequestContext,
  headers: Record<string, string>,
  opts: { fullName: string; status?: 'ACTIVE' | 'COMPLETED'; gender?: string }
) {
  const res = await request.post(`${API}/patients/`, {
    headers,
    data: {
      mr_number: uniqueId('QA-MR'),
      file_number: uniqueId('QA-F'),
      full_name: opts.fullName,
      cnic: '44455-4445555-4',
      gender: opts.gender ?? 'Female',
      room: 'Room 10',
      assigned_doctor: DOCTOR_NAME,
      procedure_category: 'Consultation',
    },
  });
  const patient = await res.json();
  if (opts.status) {
    await request.patch(`${API}/patients/${patient.id}/status`, { headers, data: { status: 'ACTIVE' } });
    if (opts.status === 'COMPLETED') {
      await request.patch(`${API}/patients/${patient.id}/status`, { headers, data: { status: 'COMPLETED' } });
    }
  }
  return patient;
}

/** The real WAITING/ACTIVE queue for DOCTOR_NAME right now, computed the
 *  same way routers/auth.py's logout() computes it. Used as ground truth
 *  instead of a fixed expected count -- this is the same shared dev
 *  database every other spec file in the suite writes to. */
async function realQueueForDoctor(request: import('@playwright/test').APIRequestContext, headers: Record<string, string>) {
  const [waiting, active] = await Promise.all([
    request.get(`${API}/patients/?status=WAITING`, { headers }).then((r) => r.json()),
    request.get(`${API}/patients/?status=ACTIVE`, { headers }).then((r) => r.json()),
  ]);
  return [...waiting, ...active].filter((p: any) => p.assigned_doctor === DOCTOR_NAME);
}

function readWorkbookRows(filePath: string): { headers: string[]; rows: any[][] } {
  const wb = XLSX.readFile(filePath);
  const sheet = wb.Sheets[wb.SheetNames[0]];
  const rows: any[][] = XLSX.utils.sheet_to_json(sheet, { header: 1 });
  return { headers: rows[0] as string[], rows: rows.slice(1) };
}

const EXPECTED_HEADERS = ['Queue Number', 'Patient ID', 'Patient Name', 'Age', 'Gender', 'Visit Date', 'Visit Time', 'Status', 'Doctor Name'];

test('logging out with real patients in the queue writes a real .xlsx file with the documented headers and one accurate row per queued patient', async ({ request }) => {
  const headers = await loginAsDoctorViaApi(request);
  const patientName = uniqueId('QA Export Content Patient');
  const patient = await seedPatient(request, headers, { fullName: patientName, status: 'ACTIVE', gender: 'Male' });

  const expectedQueue = await realQueueForDoctor(request, headers);
  expect(expectedQueue.some((p: any) => p.mr_number === patient.mr_number)).toBe(true);

  const before = new Set(listExportFiles());
  const res = await request.post(`${API}/auth/logout`, { headers });
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body.export_status).toMatch(/^exported:\d+$/);

  const newFiles = await waitForNewExportFile(before);
  expect(newFiles[0].startsWith(`${DOCTOR_NAME}_`)).toBe(true);
  expect(newFiles[0].endsWith('.xlsx')).toBe(true);

  const { headers: sheetHeaders, rows } = readWorkbookRows(path.join(exportsDir(), newFiles[0]));
  expect(sheetHeaders).toEqual(EXPECTED_HEADERS);
  expect(rows).toHaveLength(expectedQueue.length);

  const myRow = rows.find((r) => r[1] === patient.mr_number); // Patient ID column
  expect(myRow).toBeTruthy();
  expect(myRow![2]).toBe(patientName);                          // Patient Name
  expect(myRow![3]).toBe('N/A');                                // Age -- not tracked anywhere in the model
  expect(myRow![4]).toBe('Male');                               // Gender
  expect(String(myRow![5])).toMatch(/^\d{4}-\d{2}-\d{2}$/);     // Visit Date
  expect(myRow![7]).toBe('ACTIVE');                             // Status
  expect(myRow![8]).toBe(DOCTOR_NAME);                          // Doctor Name

  const exportedIds = new Set(rows.map((r) => r[1]));
  const expectedIds = new Set(expectedQueue.map((p: any) => p.mr_number));
  expect(exportedIds).toEqual(expectedIds);
});

test('a COMPLETED patient is correctly left out of the exported queue', async ({ request }) => {
  const headers = await loginAsDoctorViaApi(request);
  const completedName = uniqueId('QA Export Completed Patient');
  const completedPatient = await seedPatient(request, headers, { fullName: completedName, status: 'COMPLETED' });
  await seedPatient(request, headers, { fullName: uniqueId('QA Export Active Patient'), status: 'ACTIVE' });

  const before = new Set(listExportFiles());
  const res = await request.post(`${API}/auth/logout`, { headers });
  // Assert export_status BEFORE checking the filesystem -- routers/auth.py's
  // logout() swallows any exception from generate_queue_excel() into
  // export_status = "error:..." and still returns 200, so if the export
  // silently fails, "0 new files" is the only symptom you'd otherwise see.
  // This surfaces the backend's real error text instead.
  const body = await res.json();
  expect(body.export_status, `logout response: ${JSON.stringify(body)}`).toMatch(/^exported:\d+$/);

  const newFiles = await waitForNewExportFile(before);

  const { rows } = readWorkbookRows(path.join(exportsDir(), newFiles[0]));
  const exportedIds = rows.map((r) => r[1]);
  expect(exportedIds).not.toContain(completedPatient.mr_number);
});

test('two logouts spaced more than a second apart each get their own distinct export file -- the filename now carries second-level precision, fixing the old same-minute collision', async ({ request }) => {
  const headers = await loginAsDoctorViaApi(request);

  const firstOnlyPatient = uniqueId('QA Collision First Patient');
  await seedPatient(request, headers, { fullName: firstOnlyPatient, status: 'ACTIVE' });

  const beforeFirst = new Set(listExportFiles());
  const firstRes = await request.post(`${API}/auth/logout`, { headers });
  // See the comment in the "COMPLETED patient" test above: check
  // export_status first so a silently-swallowed backend export error shows
  // up here instead of masquerading as "0 new files".
  const firstBody = await firstRes.json();
  expect(firstBody.export_status, `logout response: ${JSON.stringify(firstBody)}`).toMatch(/^exported:\d+$/);

  const firstNew = await waitForNewExportFile(beforeFirst);
  const afterFirst = listExportFiles();
  const firstFilePath = path.join(exportsDir(), firstNew[0]);
  const firstSnapshot = readWorkbookRows(firstFilePath);
  expect(firstSnapshot.rows.some((r) => r[2] === firstOnlyPatient)).toBe(true);

  // Cross a full second boundary before logging out again, so the two
  // filenames -- which now include seconds -- are guaranteed to differ.
  await new Promise((resolve) => setTimeout(resolve, 1100));

  const secondPatient = uniqueId('QA Collision Second Patient');
  await seedPatient(request, headers, { fullName: secondPatient, status: 'ACTIVE' });

  const beforeSecond = new Set(afterFirst);
  const secondRes = await request.post(`${API}/auth/logout`, { headers });
  const secondBody = await secondRes.json();
  expect(secondBody.export_status, `logout response: ${JSON.stringify(secondBody)}`).toMatch(/^exported:\d+$/);

  const secondNew = await waitForNewExportFile(beforeSecond);

  // A genuinely new, second file now appears -- unlike the old behavior,
  // this second logout is NOT invisible from the filesystem's point of view.
  expect(secondNew[0]).not.toBe(firstNew[0]);

  // And the first file is untouched -- it still reflects only its own
  // original snapshot, not silently overwritten with the second one's data.
  const firstFileStillIntact = readWorkbookRows(firstFilePath);
  expect(firstFileStillIntact.rows.some((r) => r[2] === firstOnlyPatient)).toBe(true);
  expect(firstFileStillIntact.rows.some((r) => r[2] === secondPatient)).toBe(false);

  const secondSnapshot = readWorkbookRows(path.join(exportsDir(), secondNew[0]));
  expect(secondSnapshot.rows.some((r) => r[2] === firstOnlyPatient)).toBe(true);
  expect(secondSnapshot.rows.some((r) => r[2] === secondPatient)).toBe(true);
});
