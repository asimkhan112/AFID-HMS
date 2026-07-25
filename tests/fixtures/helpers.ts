import { test as base, expect, type Page, type APIRequestContext } from '@playwright/test';

export const API = 'http://localhost:8000';

// ---------------------------------------------------------------------------
// Ported in from the original QA scaffold's tests/fixtures.ts (a separate,
// test.extend-based fixture file that is being retired in favor of this
// plain-helpers module). CREDS and landingPageRegExp are added here as new,
// standalone exports -- nothing above or below this block is changed.
// ---------------------------------------------------------------------------

export type Role = 'hod' | 'doctor' | 'receptionist';

export const CREDS: Record<Role, { email: string; password: string; page: string }> = {
  hod:          { email: 'hod@afid.mil',       password: 'admin1234',  page: 'hod.html' },
  doctor:       { email: 'doctor@afid.mil',    password: 'doctor1234', page: 'doctor (1).html' },
  receptionist: { email: 'reception@afid.mil', password: 'staff1234',  page: 'staff.html' },
};

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// Login.html's portalForRole() redirects the doctor role to the literal
// filename 'doctor (1).html' -- a plain glob string can't safely match a
// filename with a space and parentheses once the browser percent-encodes it,
// so build a RegExp from the encoded, regex-escaped filename instead.
export function landingPageRegExp(fileName: string): RegExp {
  return new RegExp(escapeRegExp(encodeURI(fileName)) + '$');
}

export async function loginAs(page: Page, role: 'receptionist' | 'doctor' | 'hod' | 'admin') {
  await page.goto('/Login.html');

  // Clear any prior session first: Login.html redirects an already-authenticated
  // session straight to its portal before the login form ever renders, so a
  // second loginAs() (e.g. switching roles within one test) would otherwise
  // find no #login-email field. Wipe storage and reload to guarantee the form.
  await page.evaluate(() => {
    localStorage.removeItem('afid_token');
    localStorage.removeItem('afid_user');
  });
  await page.goto('/Login.html');
  await page.waitForSelector('#login-email');

  const credentials: Record<string, { email: string; password: string }> = {
    receptionist: { email: 'reception@afid.mil', password: 'staff1234' },
    doctor: { email: 'doctor@afid.mil', password: 'doctor1234' },
    hod: { email: 'hod@afid.mil', password: 'admin1234' },
    admin: { email: 'hod@afid.mil', password: 'admin1234' },
  };

  const creds = credentials[role];
  await page.fill('#login-email', creds.email);
  await page.fill('#login-password', creds.password);
  await page.click('#login-btn');
  
  // Wait for navigation to complete
  await page.waitForURL((url) => !url.pathname.includes('Login.html'), { timeout: 10000 } as any);
}

export async function authHeaders(page: Page) {
  // Get token from localStorage
  const token = await page.evaluate(() => localStorage.getItem('afid_token'));
  return {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json',
  };
}

export function uniqueId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export async function fillPatientForm(page: Page, data: {
  mr: string;
  file: string;
  name: string;
  cnic: string;
  doctor?: string;
}) {
  await page.fill('#p-mr', data.mr);
  await page.fill('#p-file', data.file);
  await page.fill('#p-name', data.name);
  await page.fill('#p-cnic', data.cnic);
  
  if (data.doctor) {
    // #p-doctor options carry a room suffix in their visible label
    // (e.g. "Dr. Rehan M. (Room 11)") while their VALUE is the plain
    // doctor name, so match by value rather than by label.
    const doctorSelect = page.locator('#p-doctor');
    await doctorSelect.selectOption(data.doctor);
  }
}

export function rowFor(page: Page, mr: string) {
  return page.locator(`tr:has(td:has-text("${mr}"))`);
}

// ---------------------------------------------------------------------------
// Suite-wide QA-patient cleanup.
//
// Nearly every spec file seeds ACTIVE/WAITING patients (mr_number is always
// uniqueId('QA-MR-...') via the helper above) against a handful of shared
// doctor identities (most commonly CREDS.doctor's 'Dr. Asadullah Khan'), but
// very few of those files ever transition what they seed to COMPLETED
// afterward -- POST /auth/logout, for example, only ever *exports* the
// queue, it never changes patient status. Within one sequential
// --workers=1 suite run, that means patients seeded by an EARLIER spec file
// are still WAITING/ACTIVE when a LATER spec file runs and asserts on
// doctor queue counts, "Total Completed Procedures" totals, or the logout
// export queue -- tests/doctor/my-analytics.spec.ts and
// tests/auth/logout-export.spec.ts have both broken this way in practice.
//
// Rather than have every spec file hand-track and clean up its own seeded
// patient IDs, every test in the suite now gets this sweep automatically:
// after each test finishes (pass or fail), complete every still-WAITING or
// -ACTIVE patient whose mr_number carries the QA-seeded prefix. This is an
// "auto" fixture on the `test` object exported below -- Playwright runs it
// around every test that uses THIS test object, with no per-test opt-in
// needed. To take effect, every spec file must import `test`/`expect` from
// this module instead of directly from '@playwright/test' (already true for
// every other named helper here, e.g. loginAs/uniqueId/CREDS).
//
// This intentionally does NOT delete rows (unlike
// AFID backend/cleanup_qa_test_data.py, which remains the tool for a full
// periodic reset across RUNS) -- it just neutralizes WAITING/ACTIVE-ness so
// counts and queues seen by whatever test runs next stay accurate, cheaply,
// after every single test rather than only when someone remembers to run
// the standalone script. Wrapped in try/catch throughout and never rethrows,
// so a cleanup hiccup (e.g. a token expiring) can never fail or mask the
// result of the test that just ran -- it's best-effort, not load-bearing.
export const test = base.extend<{ qaPatientCleanup: void }>({
  qaPatientCleanup: [
    async ({ request }, use) => {
      await use();

      try {
        const loginRes = await request.post(`${API}/auth/login`, {
          data: { email: CREDS.doctor.email, password: CREDS.doctor.password },
        });
        if (!loginRes.ok()) return;
        const { access_token } = await loginRes.json();
        const headers = { Authorization: `Bearer ${access_token}` };

        const [waitingRes, activeRes] = await Promise.all([
          request.get(`${API}/patients/?status=WAITING`, { headers }),
          request.get(`${API}/patients/?status=ACTIVE`, { headers }),
        ]);
        if (!waitingRes.ok() || !activeRes.ok()) return;
        const waiting = await waitingRes.json();
        const active = await activeRes.json();

        const all = [...waiting, ...active];
        const toComplete = all.filter(
          (p: any) => typeof p.mr_number === 'string' && p.mr_number.startsWith('QA-MR-')
        );
        if (toComplete.length === 0) return;

        await Promise.all(
          toComplete.map((p: any) =>
            request
              .patch(`${API}/patients/${p.id}/status`, { headers, data: { status: 'COMPLETED' } })
              .catch(() => {})
          )
        );
      } catch {
        // best-effort -- never fail or mask the result of the test that just ran
      }
    },
    { auto: true },
  ],
});

export { expect };