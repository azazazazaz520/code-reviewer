export interface DesktopRuntimeInfo {
  mode: "development" | "production";
  apiBaseUrl: string;
  dataDir: string;
  appVersion: string;
}

interface DesktopRuntimeBridge {
  getInfo: () => Promise<DesktopRuntimeInfo>;
  chooseDirectory: () => Promise<string | null>;
}

declare global {
  interface Window {
    desktop?: DesktopRuntimeBridge;
  }
}

export async function getDesktopRuntime(): Promise<DesktopRuntimeInfo | null> {
  if (!window.desktop) return null;
  return window.desktop.getInfo();
}
