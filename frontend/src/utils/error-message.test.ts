import { describe, expect, it } from "vitest";
import { toUserError } from "./error-message";

describe("toUserError", () => {
  it("将服务不可用状态转换为稳定的用户说明并保留诊断信息", () => {
    const result = toUserError(
      { response: { status: 502 }, code: "ERR_BAD_GATEWAY", message: "Request failed with status code 502" },
      "加载失败",
    );

    expect(result.message).toBe("审查服务暂时不可用，请确认服务已启动后重试。");
    expect(result.diagnostic).toContain("HTTP 502");
    expect(result.diagnostic).toContain("ERR_BAD_GATEWAY");
  });

  it("保留后端返回的用户可理解业务说明", () => {
    const result = toUserError({ response: { status: 400, data: { detail: "请选择审查分支" } } }, "提交失败");

    expect(result.message).toBe("请选择审查分支");
    expect(result.diagnostic).toBe("HTTP 400");
  });

  it.each([
    [401, "服务认证失败，请检查相关配置后重试。"],
    [402, "模型服务余额不足，请补充余额或更换服务后重试。"],
    [429, "请求过于频繁，请稍后重试。"],
    [503, "审查服务暂时不可用，请确认服务已启动后重试。"],
  ])("映射 HTTP %s 的恢复说明", (status, message) => {
    expect(toUserError({ response: { status } }, "请求失败").message).toBe(message);
  });

  it("不会把底层 Axios 文案直接展示为未知错误", () => {
    const result = toUserError({ message: "Network Error", code: "ERR_NETWORK" }, "无法加载仓库列表");

    expect(result.message).toBe("无法连接到审查服务，请检查服务状态或网络。");
    expect(result.diagnostic).toContain("ERR_NETWORK");
  });
});
