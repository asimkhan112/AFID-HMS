/**
 * build.mjs — produces the deployable site in dist/.
 *
 * These portals are plain static files: each HTML page carries its own inline
 * script and loads api.js as a CLASSIC script, relying on the globals it defines
 * (api, getToken, uiAlert, …). There is nothing to bundle.
 *
 * `vite build` is actively wrong here. Vite has exactly ONE entry by default --
 * index.html -- so it emitted a 0.22 kB redirect stub and dropped Login.html,
 * doctor.html, hod.html and staff.html on the floor. Vercel then served that
 * one-file dist/ and every portal 404'd in production. Adding the pages as Vite
 * inputs would not help either: Vite rewrites <script src="api.js"> into an ES
 * module, and module scope is not global, so every inline script would break on
 * "api is not defined".
 *
 * So the build is a copy. Vite stays for local dev (`npm run dev`) only.
 */
import { cpSync, mkdirSync, rmSync, readdirSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(fileURLToPath(import.meta.url));
const out = join(root, 'dist');

// Everything the browser actually requests. Deliberately excludes package.json,
// vite.config.js, build.mjs, *.log, README files and node_modules -- none of which
// belong on a public origin.
const PAGES = [
  'index.html',
  'Login.html',
  'doctor.html',
  'hod.html',
  'staff.html',
  'orthodontic-diagnosis.html',
];
const ASSETS = ['api.js', 'clinic-bg.jpeg', 'afid-logo.png', 'afid-main-logo.jpeg'];

rmSync(out, { recursive: true, force: true });
mkdirSync(out, { recursive: true });

let bytes = 0;
for (const file of [...PAGES, ...ASSETS]) {
  const src = join(root, file);
  cpSync(src, join(out, file));
  bytes += statSync(src).size;
}

// A missing page here means a 404 in production, so fail the build loudly rather
// than shipping a site with holes -- which is exactly how this broke before.
const written = readdirSync(out);
const missing = [...PAGES, ...ASSETS].filter(f => !written.includes(f));
if (missing.length) {
  console.error(`build failed — not emitted: ${missing.join(', ')}`);
  process.exit(1);
}

console.log(`static build → dist/  (${written.length} files, ${(bytes / 1024).toFixed(0)} kB)`);
for (const f of written) console.log(`  ${f}`);
