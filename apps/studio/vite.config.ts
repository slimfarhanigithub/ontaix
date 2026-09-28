import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

/** Where the dev server forwards `/api`; the in-browser mock answers before the proxy when no API is configured. */
const apiProxy = process.env.ONTAIX_API_PROXY || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: apiProxy, changeOrigin: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
  },
});
