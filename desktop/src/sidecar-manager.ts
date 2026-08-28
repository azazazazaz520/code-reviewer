import { spawn } from "node:child_process";
import { createServer } from "node:net";
import { setTimeout as delay } from "node:timers/promises";

import type {
  AllocatePort,
  FetchReady,
  SidecarConfig,
  SidecarState,
  SpawnProcess,
} from "./types";

const defaultSpawnProcess: SpawnProcess = (command, args, options) =>
  spawn(command, args, options);

const defaultFetchReady: FetchReady = async (input, init) => {
  const response = await fetch(input, init);
  return { ok: response.ok };
};

const defaultAllocatePort: AllocatePort = () =>
  new Promise((resolve, reject) => {
    const server = createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (!address || typeof address === "string") {
        server.close();
        reject(new Error("无法获取 sidecar 动态端口"));
        return;
      }
      server.close((error) => {
        if (error) reject(error);
        else resolve(address.port);
      });
    });
  });

export class SidecarManager {
  private readonly config: Required<
    Pick<SidecarConfig, "readyTimeoutMs" | "pollIntervalMs">
  > & SidecarConfig;
  private child: ReturnType<SpawnProcess> | null = null;
  private state: SidecarState = { status: "stopped" };
  private baseUrl: string | null = null;
  private stopping = false;
  private readonly listeners = new Set<(state: SidecarState) => void>();
  private allocatedPort: number | null = null;

  constructor(config: SidecarConfig) {
    this.config = {
      readyTimeoutMs: 20_000,
      pollIntervalMs: 150,
      spawnProcess: defaultSpawnProcess,
      fetchReady: defaultFetchReady,
      allocatePort: defaultAllocatePort,
      ...config,
    };
  }

  async start(): Promise<{ baseUrl: string }> {
    if (this.state.status === "ready" && this.baseUrl) {
      return { baseUrl: this.baseUrl };
    }
    if (this.state.status === "starting") {
      throw new Error("sidecar 正在启动");
    }

    this.stopping = false;
    this.setState({ status: "starting" });

    const port = this.config.port ?? this.allocatedPort ?? (await this.config.allocatePort!());
    this.allocatedPort = port;
    const baseUrl = `http://127.0.0.1:${port}`;

    try {
      const launch = this.buildLaunchCommand(port);
      this.child = this.config.spawnProcess!(launch.command, launch.args, {
        cwd: this.config.rootDir,
        env: {
          ...process.env,
          ...(this.config.getSecretEnvironment?.() ?? {}),
          CODE_REVIEWER_DESKTOP: "1",
        },
        windowsHide: true,
        stdio: ["ignore", "pipe", "pipe"],
      });
      this.attachChildListeners();
      await this.waitUntilReady(baseUrl);
      if (!this.child || this.child.exitCode !== null) {
        throw new Error("sidecar 在就绪前退出");
      }
      this.baseUrl = baseUrl;
      this.setState({ status: "ready", baseUrl, pid: this.child.pid ?? -1 });
      return { baseUrl };
    } catch (error) {
      await this.stop();
      const message = error instanceof Error ? error.message : String(error);
      this.setState({ status: "failed", message });
      throw new Error(`sidecar 启动失败：${message}`);
    }
  }

  async stop(): Promise<void> {
    const child = this.child;
    this.stopping = true;
    this.child = null;
    this.baseUrl = null;

    if (!child || child.exitCode !== null) {
      this.setState({ status: "stopped" });
      return;
    }

    const exited = new Promise<void>((resolve) => {
      child.once("exit", () => resolve());
    });
    child.kill();
    await Promise.race([exited, delay(3_000)]);
    if (child.exitCode === null) {
      child.kill("SIGKILL");
    }
    this.setState({ status: "stopped" });
  }

  async restart(): Promise<{ baseUrl: string }> {
    await this.stop();
    return this.start();
  }

  getState(): SidecarState {
    return this.state;
  }

  onStateChange(listener: (state: SidecarState) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private buildLaunchCommand(port: number): { command: string; args: string[] } {
    const commonArgs = [
      "--host",
      "127.0.0.1",
      "--port",
      String(port),
      "--data-dir",
      this.config.dataDir,
    ];

    if (this.config.mode === "development") {
      if (!this.config.pythonExecutable) {
        throw new Error("未找到 Python 解释器");
      }
      return {
        command: this.config.pythonExecutable,
        args: ["-m", "app.desktop_entry", ...commonArgs],
      };
    }

    if (!this.config.backendExecutable) {
      throw new Error("未找到打包后的 backend sidecar");
    }
    return {
      command: this.config.backendExecutable,
      args: [
        ...commonArgs,
        ...(this.config.frontendDist
          ? ["--frontend-dist", this.config.frontendDist]
          : []),
      ],
    };
  }

  private attachChildListeners(): void {
    if (!this.child) return;
    this.child.stdout?.on("data", (chunk: Buffer) => this.log(chunk));
    this.child.stderr?.on("data", (chunk: Buffer) => this.log(chunk));
    this.child.once("error", (error) => {
      if (!this.stopping) {
        const message = error instanceof Error ? error.message : String(error);
        this.setState({ status: "failed", message });
      }
    });
    this.child.once("exit", (code) => {
      if (!this.stopping && this.state.status !== "ready") {
        this.setState({
          status: "failed",
          message: "sidecar exited unexpectedly",
          exitCode: typeof code === "number" ? code : null,
        });
      }
    });
  }

  private async waitUntilReady(baseUrl: string): Promise<void> {
    const deadline = Date.now() + this.config.readyTimeoutMs;
    let lastError = "服务尚未就绪";

    while (Date.now() < deadline) {
      if (this.child?.exitCode !== null) {
        throw new Error("sidecar 在探活前退出");
      }
      try {
        const result = await this.config.fetchReady!(
          `${baseUrl}/api/ready`,
          { signal: AbortSignal.timeout(2_000) },
        );
        if (result.ok) return;
        lastError = "sidecar 返回非成功状态";
      } catch (error) {
        lastError = error instanceof Error ? error.message : String(error);
      }
      await delay(this.config.pollIntervalMs);
    }

    throw new Error(`等待 sidecar 就绪超时：${lastError}`);
  }

  private log(chunk: Buffer): void {
    const line = chunk.toString("utf8").trim();
    if (line) this.config.onLog?.(line);
  }

  private setState(state: SidecarState): void {
    this.state = state;
    for (const listener of this.listeners) listener(state);
  }
}
