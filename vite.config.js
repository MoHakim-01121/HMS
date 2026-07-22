import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { resolve } from "path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  root: resolve("./frontend"),
  base: "/static/dist/",
  resolve: {
    alias: {
      "@": resolve("./frontend"),
    },
  },
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
