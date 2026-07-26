import { defineConfig } from "vite";

export default defineConfig({
  root: "AFID frontend",
  server: {
    port: 5173,
    // Forward every backend path prefix to the local API. Prefix form (no
    // trailing "/.*") so both "/allocations" and "/allocations/1" match.
    // Mirrors the production rewrites in AFID frontend/AFID frontend/vercel.json.
    proxy: {
      "^/auth": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "^/patients": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "^/doctors": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "^/allocations": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "^/procedures": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "^/leaves": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "^/staff": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "^/hod": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "^/presets": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
