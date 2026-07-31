import { defineConfig } from "vite";

// DEV SERVER ONLY. The production build is `node build.mjs` (see package.json), not
// `vite build` -- Vite builds a single entry (index.html) and would ship only the
// redirect stub, dropping every portal page. See build.mjs for the full reasoning.
export default defineConfig({
  root: ".",
  server: {
    port: 5173,
    // One rule, mirroring the single "/api/:path*" rewrite in
    // AFID frontend/vercel.json: strip the "/api" prefix and forward the rest
    // to the local backend.
    //
    // Routing every call under one prefix also removes a whole class of
    // conflicts with the static pages. Per-resource prefixes used to collide
    // with the portal filenames themselves -- "^/staff" matched "/staff.html"
    // and "^/hod" matched "/hod.html", so logging in as a receptionist or HOD
    // proxied the portal page to the API and rendered {"detail":"Not Found"}.
    proxy: {
      "^/api/": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
