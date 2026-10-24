import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

function fallbackIndex() {
  return {
    name: "fallback-index",
    configureServer(server: { middlewares: { use: (fn: (req: { url?: string }, _res: unknown, next: () => void) => void) => void } }) {
      server.middlewares.use((req, _res, next) => {
        if (req.url === "/fallback" || req.url === "/fallback/") {
          req.url = "/fallback/index.html";
        }
        next();
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), fallbackIndex()],
  server: {
    port: 5173,
    proxy: {
      // Override with VITE_API_PROXY=http://localhost:8000 when the API runs elsewhere.
      "/api": process.env.VITE_API_PROXY || "http://localhost:8001",
    },
  },
});
