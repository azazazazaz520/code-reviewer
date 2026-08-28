import fs from "node:fs";
import path from "node:path";

import { safeStorage } from "electron";

export type SecretProvider = "llm" | "github" | "gitee";

const environmentNames: Record<SecretProvider, string> = {
  llm: "DEEPSEEK_API_KEY",
  github: "GITHUB_TOKEN",
  gitee: "GITEE_TOKEN",
};

type StoredSecrets = Partial<Record<SecretProvider, string>>;

export class SecretStore {
  constructor(private readonly filePath: string) {}

  get(provider: SecretProvider): string | null {
    const stored = this.read();
    const encoded = stored[provider];
    if (!encoded || !safeStorage.isEncryptionAvailable()) return null;
    try {
      return safeStorage.decryptString(Buffer.from(encoded, "base64"));
    } catch {
      return null;
    }
  }

  set(provider: SecretProvider, value: string): void {
    const clean = value.trim();
    if (!clean) throw new Error("密钥不能为空");
    if (!safeStorage.isEncryptionAvailable()) {
      throw new Error("当前系统暂不支持安全存储，请改用环境配置");
    }
    const stored = this.read();
    stored[provider] = safeStorage.encryptString(clean).toString("base64");
    this.write(stored);
  }

  clear(provider: SecretProvider): void {
    const stored = this.read();
    delete stored[provider];
    this.write(stored);
  }

  environment(): Record<string, string> {
    const environment: Record<string, string> = {};
    for (const provider of Object.keys(environmentNames) as SecretProvider[]) {
      const value = this.get(provider);
      if (value) environment[environmentNames[provider]] = value;
    }
    return environment;
  }

  private read(): StoredSecrets {
    try {
      if (!fs.existsSync(this.filePath)) return {};
      const value: unknown = JSON.parse(fs.readFileSync(this.filePath, "utf8"));
      if (!value || typeof value !== "object") return {};
      return value as StoredSecrets;
    } catch {
      throw new Error("安全凭据文件无法读取");
    }
  }

  private write(value: StoredSecrets): void {
    const directory = path.dirname(this.filePath);
    fs.mkdirSync(directory, { recursive: true });
    const temporaryPath = `${this.filePath}.${process.pid}.tmp`;
    try {
      fs.writeFileSync(temporaryPath, JSON.stringify(value), { encoding: "utf8", mode: 0o600 });
      fs.renameSync(temporaryPath, this.filePath);
    } catch (error) {
      try { fs.rmSync(temporaryPath, { force: true }); } catch { /* 保留原文件，避免破坏已有凭据。 */ }
      throw error;
    }
  }
}
