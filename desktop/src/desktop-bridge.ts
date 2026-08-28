import { dialog, ipcMain, shell } from "electron";

import type { AppConfig } from "./app-config";
import { BACKEND_STATE_CHANNEL } from "./channels";
import type { SidecarManager } from "./sidecar-manager";
import { SecretStore, type SecretProvider } from "./secret-store";
import type { DesktopRuntimeInfo } from "./types";

export function registerDesktopBridge(options: {
  appConfig: AppConfig;
  appVersion: string;
  sidecar: SidecarManager;
  secretStore: SecretStore;
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

  ipcMain.handle("desktop:save-secret", async (_event, provider: unknown, value: unknown) => {
    if (!isSecretProvider(provider) || typeof value !== "string") {
      return { ok: false, error: "凭据参数无效" };
    }
    const previous = options.secretStore.get(provider);
    try {
      options.secretStore.set(provider, value);
      await options.sidecar.restart();
      return { ok: true };
    } catch (error) {
      try {
        if (previous) options.secretStore.set(provider, previous);
        else options.secretStore.clear(provider);
      } catch {
        // 恢复失败时保留原异常，避免把凭据内容写入错误消息。
      }
      return { ok: false, error: error instanceof Error ? error.message : "凭据保存失败" };
    }
  });

  ipcMain.handle("desktop:clear-secret", async (_event, provider: unknown) => {
    if (!isSecretProvider(provider)) return { ok: false, error: "凭据参数无效" };
    const previous = options.secretStore.get(provider);
    try {
      options.secretStore.clear(provider);
      await options.sidecar.restart();
      return { ok: true };
    } catch (error) {
      try { if (previous) options.secretStore.set(provider, previous); } catch { /* 保留原凭据，避免清除失败造成丢失。 */ }
      return { ok: false, error: error instanceof Error ? error.message : "凭据清除失败" };
    }
  });
}

function isSecretProvider(value: unknown): value is SecretProvider {
  return value === "llm" || value === "github" || value === "gitee";
}
