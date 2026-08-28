import fs from "node:fs";
import path from "node:path";

import type { App } from "electron";

import type { SidecarConfig } from "./types";

export interface AppConfig {
  mode: "development" | "production";
  rootDir: string;
  dataDir: string;
  secretsFile: string;
  frontendDist: string;
  backendExecutable: string;
  pythonExecutable: string;
  devServerUrl: string;
}

export function createAppConfig(options: {
  mode: "development" | "production";
  rootDir: string;
  userDataDir: string;
  resourcesDir: string;
  devServerUrl?: string;
  platform?: NodeJS.Platform;
}): AppConfig {
  const platform = options.platform ?? process.platform;
  const dataDir = path.join(options.userDataDir, "data");
  const frontendDist = path.join(options.resourcesDir, "frontend");
  const backendExecutable = path.join(
    options.resourcesDir,
    "backend",
    platform === "win32" ? "code-reviewer-backend.exe" : "code-reviewer-backend",
  );
  const pythonExecutable = path.join(
    options.rootDir,
    "backend",
    platform === "win32" ? ".venv\\Scripts\\python.exe" : ".venv/bin/python",
  );

  return {
    mode: options.mode,
    rootDir: options.rootDir,
    dataDir,
    secretsFile: path.join(dataDir, "secrets.json"),
    frontendDist,
    backendExecutable,
    pythonExecutable: fs.existsSync(pythonExecutable)
      ? pythonExecutable
      : platform === "win32"
        ? "python.exe"
        : "python3",
    devServerUrl: options.devServerUrl ?? "http://127.0.0.1:5173",
  };
}

export function createSidecarConfig(config: AppConfig): SidecarConfig {
  return {
    mode: config.mode,
    rootDir: config.mode === "development" ? path.join(config.rootDir, "backend") : config.rootDir,
    dataDir: config.dataDir,
    pythonExecutable: config.pythonExecutable,
    backendExecutable: config.backendExecutable,
    frontendDist: config.frontendDist,
  };
}

export function getAppRoot(app: Pick<App, "isPackaged" | "getAppPath">): string {
  return app.isPackaged ? process.resourcesPath : path.resolve(app.getAppPath(), "..");
}
