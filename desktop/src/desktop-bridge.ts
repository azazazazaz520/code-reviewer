import { dialog, ipcMain, shell } from "electron";

import type { AppConfig } from "./app-config";
import { BACKEND_STATE_CHANNEL } from "./channels";
import type { SidecarManager } from "./sidecar-manager";
import type { DesktopRuntimeInfo } from "./types";

export function registerDesktopBridge(options: {
  appConfig: AppConfig;
  appVersion: string;
  sidecar: SidecarManager;
}): void {
  ipcMain.handle("desktop:get-info", (): DesktopRuntimeInfo => {
    const state = options.sidecar.getState();
    return {
      mode: options.appConfig.mode,
      apiBaseUrl: state.status === "ready" ? state.baseUrl : "",
      dataDir: options.appConfig.dataDir,
      appVersion: options.appVersion,
    };
  });

  ipcMain.handle("desktop:choose-directory", async () => {
    const result = await dialog.showOpenDialog({
      properties: ["openDirectory", "createDirectory"],
    });
    return result.canceled ? null : result.filePaths[0] ?? null;
  });

  ipcMain.handle("desktop:open-path", async (_event, requestedPath: unknown) => {
    if (typeof requestedPath !== "string" || !requestedPath.trim()) {
      return { ok: false, error: "路径不能为空" };
    }
    const error = await shell.openPath(requestedPath);
    return error ? { ok: false, error } : { ok: true };
  });
}
