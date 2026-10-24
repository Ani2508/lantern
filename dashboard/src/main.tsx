import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "@fontsource-variable/inter";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/700.css";
import "leaflet/dist/leaflet.css";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/layout.css";
import "./styles/map.css";
import "./styles/panels.css";
import "./styles/story.css";

// Apply the saved theme before first paint to avoid a flash.
try {
  const t = localStorage.getItem("lantern.theme");
  document.documentElement.dataset.theme = t === "light" ? "light" : "dark";
} catch {
  document.documentElement.dataset.theme = "dark";
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
