export type SidecarState =
  | { status: "stopped" }
  | { status: "starting" }
  | { status: "ready"; baseUrl: string; pid: number }
  | { status: "failed"; message: string; exitCode?: number | null };

export interface DesktopRuntimeInfo {
  mode: "development" | "production";
  apiBaseUrl: string;
  dataDir: string;
  appVersion: string;
}

export interface DesktopRuntimeBridge {
  getInfo: () => Promise<DesktopRuntimeInfo>;
  chooseDirectory: () => Promise<string | null>;
  openPath: (requestedPath: string) => Promise<{ ok: boolean; error?: string }>;
  onBackendState: (listener: (state: SidecarState) => void) => () => void;
}

declare global {
  interface Window {
    desktop?: DesktopRuntimeBridge;
  }
}

export async function getDesktopRuntime(): Promise<DesktopRuntimeInfo | null> {
  const bridge = getDesktopBridge();
  if (!bridge) return null;
  return bridge.getInfo();
}

export function getDesktopBridge(): DesktopRuntimeBridge | null {
  if (typeof window === "undefined" || !window.desktop) return null;
  return window.desktop;
}
