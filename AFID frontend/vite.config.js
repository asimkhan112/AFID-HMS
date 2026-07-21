import { defineConfig } from "vite";

export default defineConfig({
  root: "AFID frontend",
  server: {
    port: 5173,
    proxy: {
      "^/auth/.*": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "^/patients/.*": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "^/doctors/.*": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "^/procedures/.*": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "^/leaves/.*": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "^/staff/.*": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "^/hod/.*": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
