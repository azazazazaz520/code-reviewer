import path from "node:path";

import {
  app,
  BrowserWindow,
  dialog,
  ipcMain,
  Menu,
} from "electron";

import { createAppConfig, createSidecarConfig, getAppRoot } from "./app-config";
import { BACKEND_STATE_CHANNEL } from "./channels";
import { registerDesktopBridge } from "./desktop-bridge";
import { SecretStore } from "./secret-store";
import { SidecarManager } from "./sidecar-manager";

let mainWindow: BrowserWindow | null = null;
let sidecar: SidecarManager | null = null;

const hasSingleInstance = app.requestSingleInstanceLock();

if (!hasSingleInstance) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (!mainWindow) return;
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  });

  app.whenReady().then(startApplication).catch(handleStartupFailure);

  app.on("window-all-closed", () => {
    if (process.platform !== "darwin") app.quit();
  });

  app.on("before-quit", (event) => {
    if (!sidecar) return;
    event.preventDefault();
    const current = sidecar;
    sidecar = null;
    void current.stop().finally(() => app.exit(0));
  });
}

async function startApplication(): Promise<void> {
  Menu.setApplicationMenu(null);

  const mode = app.isPackaged ? "production" : "development";
  const appConfig = createAppConfig({
    mode,
    rootDir: getAppRoot(app),
    userDataDir: app.getPath("userData"),
    resourcesDir: process.resourcesPath,
    devServerUrl: process.env.CODE_REVIEWER_DEV_SERVER_URL,
  });

  const secretStore = new SecretStore(appConfig.secretsFile);

  sidecar = new SidecarManager({
    ...createSidecarConfig(appConfig),
    getSecretEnvironment: () => secretStore.environment(),
    onLog: (line) => console.log(`[sidecar] ${line}`),
  });
  registerDesktopBridge({
    appConfig,
    appVersion: app.getVersion(),
    sidecar,
    secretStore,
  });

  const runtime = await sidecar.start();
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 960,
    minWidth: 1024,
    minHeight: 720,
    title: "Code Reviewer",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  mainWindow.webContents.on("page-title-updated", (event) => {
    event.preventDefault();
    mainWindow?.setTitle("Code Reviewer");
  });

  mainWindow.webContents.on("preload-error", (_event, preloadPath, error) => {
    console.error(`[desktop] preload failed: ${preloadPath}`, error);
  });

  sidecar.onStateChange((state) => {
    mainWindow?.webContents.send(BACKEND_STATE_CHANNEL, state);
  });

  if (appConfig.mode === "development") {
    await mainWindow.loadURL(appConfig.devServerUrl);
  } else {
    await mainWindow.loadURL(runtime.baseUrl);
  }

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

function handleStartupFailure(error: unknown): void {
  const message = error instanceof Error ? error.message : String(error);
  dialog.showErrorBox("Code Reviewer 启动失败", message);
  app.quit();
}

ipcMain.on("desktop:open-devtools", () => mainWindow?.webContents.openDevTools());
