import { EventEmitter } from "node:events";
import { Readable } from "node:stream";
import { test } from "node:test";
import assert from "node:assert/strict";

import { SidecarManager } from "./sidecar-manager";

class FakeChild extends EventEmitter {
  pid = 1234;
  exitCode: number | null = null;
  stdout = new Readable({ read() {} });
  stderr = new Readable({ read() {} });

  kill(): boolean {
    this.exitCode = 0;
    this.emit("exit", 0, null);
    return true;
  }
}

test("SidecarManager starts, waits for ready, and stops the child process", async () => {
  const child = new FakeChild();
  let command = "";
  let args: string[] = [];

  const manager = new SidecarManager({
    mode: "development",
    rootDir: "C:/repo/backend",
    dataDir: "C:/data",
    pythonExecutable: "python.exe",
    allocatePort: async () => 43123,
    spawnProcess: (receivedCommand, receivedArgs) => {
      command = receivedCommand;
      args = receivedArgs;
      return child;
    },
    fetchReady: async (url) => ({ ok: url === "http://127.0.0.1:43123/api/ready" }),
  });

  const runtime = await manager.start();

  assert.equal(runtime.baseUrl, "http://127.0.0.1:43123");
  assert.equal(command, "python.exe");
  assert.deepEqual(args.slice(0, 2), ["-m", "app.desktop_entry"]);
  assert.equal(manager.getState().status, "ready");

  await manager.stop();
  assert.equal(manager.getState().status, "stopped");
});
