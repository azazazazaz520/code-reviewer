export type SidecarState =
  | { status: "stopped" }
  | { status: "starting" }
  | { status: "ready"; baseUrl: string; pid: number }
  | { status: "failed"; message: string; exitCode?: number | null };

export interface SpawnedChild {
  pid?: number;
  exitCode: number | null;
  stdout?: NodeJS.ReadableStream;
  stderr?: NodeJS.ReadableStream;
  on(event: string, listener: (...args: unknown[]) => void): this;
  once(event: string, listener: (...args: unknown[]) => void): this;
  kill(signal?: NodeJS.Signals): boolean;
}

export type SpawnProcess = (
  command: string,
  args: string[],
  options: {
    cwd: string;
    env: NodeJS.ProcessEnv;
    windowsHide: boolean;
    stdio: ["ignore", "pipe", "pipe"];
  },
) => SpawnedChild;

export type FetchReady = (
  input: string,
  init?: RequestInit,
) => Promise<{ ok: boolean }>;

export type AllocatePort = () => Promise<number>;

export interface SidecarConfig {
  mode: "development" | "production";
  rootDir: string;
  dataDir: string;
  pythonExecutable?: string;
  backendExecutable?: string;
  frontendDist?: string;
  port?: number;
  readyTimeoutMs?: number;
  pollIntervalMs?: number;
  spawnProcess?: SpawnProcess;
  fetchReady?: FetchReady;
  allocatePort?: AllocatePort;
  onLog?: (line: string) => void;
}

export interface DesktopRuntimeInfo {
  mode: "development" | "production";
  apiBaseUrl: string;
  dataDir: string;
  appVersion: string;
}
