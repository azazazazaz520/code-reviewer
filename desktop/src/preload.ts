import { contextBridge, ipcRenderer } from "electron";

import type { DesktopRuntimeInfo, SidecarState } from "./types";
import type { SecretProvider } from "./secret-store";

// Keep the sandboxed preload self-contained: it may require Electron's built-ins,
// but it must not depend on another local CommonJS module.
const BACKEND_STATE_CHANNEL = "desktop:backend-state";

const desktopRuntime = {
  getInfo: (): Promise<DesktopRuntimeInfo> => ipcRenderer.invoke("desktop:get-info"),
  chooseDirectory: (): Promise<string | null> =>
    ipcRenderer.invoke("desktop:choose-directory"),
  openPath: (requestedPath: string): Promise<{ ok: boolean; error?: string }> =>
    ipcRenderer.invoke("desktop:open-path", requestedPath),
  saveSecret: (provider: SecretProvider, value: string): Promise<{ ok: boolean; error?: string }> =>
    ipcRenderer.invoke("desktop:save-secret", provider, value),
  clearSecret: (provider: SecretProvider): Promise<{ ok: boolean; error?: string }> =>
    ipcRenderer.invoke("desktop:clear-secret", provider),
  onBackendState: (listener: (state: SidecarState) => void): (() => void) => {
    const handler = (_event: Electron.IpcRendererEvent, state: SidecarState) =>
      listener(state);
    ipcRenderer.on(BACKEND_STATE_CHANNEL, handler);
    return () => ipcRenderer.removeListener(BACKEND_STATE_CHANNEL, handler);
  },
};

contextBridge.exposeInMainWorld("desktop", desktopRuntime);
