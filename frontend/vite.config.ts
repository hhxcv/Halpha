import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    sourcemap: false,
    // The running local app serves this directory directly. Keep hashed chunks
    // from the previous build so already-open pages can still lazy-load them.
    emptyOutDir: false,
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": "http://127.0.0.1:8765",
      "/operations": "http://127.0.0.1:8765",
    },
  },
});
