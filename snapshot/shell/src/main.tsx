import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import "./i18n";
import "./dizz-tokens.css";   // K2.2/K2.4 Token-Master (Kopie von shared/dizz-tokens.css)
import "./controls.css";      // K2.4 Control-Familie (Kopie von news/ui-kit/controls.css)
import "./theme.css";         // Core-Eigenheiten + Alias der Token-Namen (zuletzt)
import "./clickwave.css";     // Klick-Wellen-Effekt (DzWave) — Styles (token-/design-abhängig, Kopie aus packages/ui-kit)
import "./clickwave.js";      // Klick-Wellen-Effekt — Engine (window.DzWave, Auto-Init)

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
