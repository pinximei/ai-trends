import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { hasSsrHomeMarkup } from "@/lib/ssrHomeBootstrap";
import "./index.css";

const rootEl = document.getElementById("root");
if (!rootEl) {
  throw new Error("root element missing");
}

const app = (
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

if (hasSsrHomeMarkup()) {
  ReactDOM.hydrateRoot(rootEl, app);
} else {
  ReactDOM.createRoot(rootEl).render(app);
}
