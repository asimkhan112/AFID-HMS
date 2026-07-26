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

// ---------------------------------------------------------------------------
// Leave-request fixtures.
//
// routers/leaves.py now enforces two rules that make hardcoded calendar dates
// unusable in tests:
//   * a start date in the past is refused outright, so any fixed date
//     eventually rots as real time passes;
//   * a second PENDING request that OVERLAPS an existing one from the same
//     requester is refused -- that duplicate-suppression is what stops a single
//     request appearing repeatedly in the HOD's approval queue, and it also
//     means a re-run of the same test would collide with its own leftovers.
// ---------------------------------------------------------------------------

/** A date `offsetDays` from today as YYYY-MM-DD (local, no timezone drift). */
export function dayOffset(offsetDays: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/** A future, non-past leave window suitable for POST /leaves/. */
export function futureLeaveWindow(lengthDays = 2): { start_date: string; end_date: string } {
  const start = 30 + Math.floor(Math.random() * 900);
  return { start_date: dayOffset(start), end_date: dayOffset(start + lengthDays) };
}

/**
 * Deletes the caller's own PENDING leave requests so a fresh one cannot be
 * refused as an overlap of a previous run's leftovers.
 *
 * Pass DOCTOR/RECEPTIONIST headers only -- GET /leaves/ returns every user's
 * requests for an HOD/admin token, and this would then clear the whole queue.
 */
export async function clearOwnPendingLeaves(
  request: APIRequestContext,
  headers: Record<string, string>
) {
  const res = await request.get(`${API}/leaves/`, { headers });
  if (!res.ok()) return;
  for (const leave of await res.json()) {
    if (String(leave.status || '').toUpperCase() === 'PENDING') {
      await request.delete(`${API}/leaves/${leave.id}`, { headers });
    }
  }
}

// ---------------------------------------------------------------------------
// In-page dialogs (api.js: uiAlert / uiConfirm / uiPrompt).
//
// The portals no longer call window.alert/confirm/prompt -- the browser
// prefixes those with the page origin ("localhost:5173 says…"), which reads as
// a browser warning rather than part of the application. They are replaced by
// an in-page dialog rendered as `.afid-dlg`, so tests drive DOM elements here
// instead of Playwright's page.on('dialog') handler.
// ---------------------------------------------------------------------------

export const DIALOG = '.afid-dlg';

/** Text of the currently-open in-page dialog, or null when none is open. */
export async function dialogText(page: Page): Promise<string | null> {
  const box = page.locator(`${DIALOG} .afid-dlg-body`);
  if (await box.count() === 0) return null;
  return (await box.first().innerText()).trim();
}

// Waits for THIS dialog element to go away, not merely for the `.afid-dlg`
// selector to stop matching. A flow that chains two prompts (Add Procedure
// asks for a name, then a duration) opens the next dialog in the same tick the
// previous one closes, so a selector-based detach wait would never be satisfied.
async function closeDialog(page: Page, click: (dlg: ReturnType<Page['locator']>) => Promise<void>) {
  await page.waitForSelector(DIALOG, { timeout: 10000 });
  const handle = await page.locator(DIALOG).first().elementHandle();
  await click(page.locator(DIALOG).first());
  if (handle) {
    await page.waitForFunction((el) => !el.isConnected, handle, { timeout: 10000 });
    await handle.dispose();
  }
}

/** Confirm/accept the open dialog. `value` fills a prompt dialog's input. */
export async function acceptDialog(page: Page, value?: string) {
  await closeDialog(page, async (dlg) => {
    if (value !== undefined) await dlg.locator('.afid-dlg-input').fill(value);
    await dlg.locator('.afid-dlg-btn.primary').click();
  });
}

/** Cancel/dismiss the open dialog. */
export async function dismissDialog(page: Page) {
  await closeDialog(page, async (dlg) => {
    const ghost = dlg.locator('.afid-dlg-btn.ghost');
    if (await ghost.count()) await ghost.click();
    else await page.keyboard.press('Escape');
  });
}

/** Dismiss a dialog only if one happens to be open; never throws. */
export async function dismissDialogIfOpen(page: Page) {
  if (await page.locator(DIALOG).count()) {
    await dismissDialog(page).catch(() => {});
  }
}

export async function fillPatientForm(page: Page, data: {
  mr: string;
  file: string;
  name: string;
  cnic: string;
  doctor?: string;
  gender?: string;
  bloodGroup?: string;
  serviceProfile?: string;
}) {
  await page.fill('#p-mr', data.mr);
  await page.fill('#p-file', data.file);
  await page.fill('#p-name', data.name);
  await page.fill('#p-cnic', data.cnic);

  // Gender / blood group / service profile are now part of the registration
  // form and are required, so fill sensible defaults unless overridden.
  await page.selectOption('#p-gender', data.gender ?? 'Male');
  await page.selectOption('#p-blood', data.bloodGroup ?? 'O+');
  await page.selectOption('#p-service-profile', data.serviceProfile ?? 'Serving Officer');

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