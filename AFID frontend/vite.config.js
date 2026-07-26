import { defineConfig } from "vite";

export default defineConfig({
  root: "AFID frontend",
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
