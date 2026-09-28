import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Frontend unit tests (Vitest + jsdom + Testing Library). Kept separate from
// vite.config.ts so the dev/build pipeline stays untouched.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
});
