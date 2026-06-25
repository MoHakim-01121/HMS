import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

export default defineConfig({
  plugins: [react()],
  root: resolve("./frontend"),
  base: "/static/dist/",
  build: {
    manifest: "manifest.json",
    outDir: resolve("./hw/static/dist"),
    emptyOutDir: true,
    rollupOptions: {
      input: resolve("./frontend/main.jsx"),
      output: {
        manualChunks: {
          vendor: ["react", "react-dom", "@inertiajs/react"],
        },
      },
    },
  },
  server: {
    host: "localhost",
    port: 5173,
    origin: "http://localhost:5173",
  },
});
