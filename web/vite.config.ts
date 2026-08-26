import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Everything goes to Isabella's API. The browser never sees the Hermes key -
// it lives server-side, in her .env, and this is the reason the UI has no
// direct line to port 8643 at all.
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
