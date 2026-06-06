import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/pnl/",
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/pnl/api": {
        target: "http://127.0.0.1:8001",
        rewrite: (path) => path.replace(/^\/pnl/, ""),
        ws: true
      },
      "/api": {
        target: "http://127.0.0.1:8001",
        ws: true
      }
    }
  },
  build: {
    outDir: "dist"
  }
});
