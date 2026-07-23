import { defineConfig, devices } from '@playwright/test';

// This config lives at the project root, alongside node_modules (moved
// here from QA/ because Node's module resolution walks UP from a spec
// file's own folder -- tests/ and QA/ are siblings, so node_modules has
// to live in a common ancestor, i.e. here, for '@playwright/test' imports
// in tests/**/*.spec.ts to resolve at all.
export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 1,
  reporter: [['html', { open: 'never' }]],
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: [
    {
      // Invoke the backend venv's own python.exe by absolute, quoted path
      // and run uvicorn as a module -- works regardless of the invoking
      // terminal's PATH/activation state. Path is quoted since
      // 'AFID backend' contains a space.
      command: '"C:\\Users\\HP\\Documents\\AFID-HMS\\AFID backend\\.venv\\Scripts\\python.exe" -m uvicorn main:app --reload --port 8000',
      cwd: './AFID backend',
      url: 'http://127.0.0.1:8000/',
      reuseExistingServer: true,
      timeout: 60_000,
    },
    {
      command: 'npm run dev',
      cwd: './AFID frontend',
      url: 'http://localhost:5173/',
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ],
});
