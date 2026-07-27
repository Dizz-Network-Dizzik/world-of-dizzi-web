import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev: Vite unter :5173, API-Aufrufe gehen an den Core (:8200).
// Build: dist/ wird vom Core selbst ausgeliefert (Muster Trading Bot).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": "http://127.0.0.1:8200" },
  },
});
