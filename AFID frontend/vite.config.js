import { defineConfig } from "vite";

export default defineConfig({
  root: "AFID frontend",
  server: {
    port: 5173,
    // Forward every backend path prefix to the local API.
    //
    // Each pattern must end at a path boundary -- "/", "?", "#", or end of
    // string. A bare prefix like "^/staff" ALSO matches the static page
    // "/staff.html", and "^/hod" matches "/hod.html", so logging in as a
    // receptionist or HOD proxied the portal page itself to the API and
    // rendered {"detail":"Not Found"} instead of the portal. (The doctor
    // portal was unaffected only because its file is "doctor (1).html" and the
    // prefix is "/doctors".) Production is unaffected: vercel.json rewrites use
    // "/staff/:path*", which already requires the trailing slash.
    proxy: {
      "^/auth(?:[/?#]|$)": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "^/patients(?:[/?#]|$)": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "^/doctors(?:[/?#]|$)": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "^/allocations(?:[/?#]|$)": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "^/procedures(?:[/?#]|$)": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "^/leaves(?:[/?#]|$)": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "^/staff(?:[/?#]|$)": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "^/hod(?:[/?#]|$)": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "^/presets(?:[/?#]|$)": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
