import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Mock mode imports the shared fixtures from ../tests/fixtures (M2), so the
// dashboard and the Python tests always use the same hour-9 story.
export default defineConfig({
  plugins: [react()],
  envDir: "..",
  server: { port: 5173, fs: { allow: [".."] } },
  build: { outDir: "dist", sourcemap: false },
});
