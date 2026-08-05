import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App.tsx";
import { ThemeProvider } from "./components/theme-provider";
import { configureApiBaseUrl } from "./api/client";
import { getDesktopRuntime } from "./runtime/desktop";

async function bootstrap(): Promise<void> {
  const runtime = await getDesktopRuntime();
  configureApiBaseUrl(runtime?.apiBaseUrl);

  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <ThemeProvider>
        <App />
      </ThemeProvider>
    </StrictMode>,
  );
}

void bootstrap();
