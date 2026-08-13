import { useCallback, useEffect, useState } from "react";
import { getDesktopBridge, getDesktopRuntime } from "../runtime/desktop";
import { settingsApi } from "../api/settings";
import type { EffectiveSettingsSnapshot } from "../types/settings";
import { toUserError, type UserErrorInfo } from "../utils/error-message";
import type { DesktopRuntimeInfo, SidecarState } from "../runtime/desktop";

interface UseSettingsResult {
  snapshot: EffectiveSettingsSnapshot | null;
  runtime: DesktopRuntimeInfo | null;
  sidecarState: SidecarState | null;
  runtimeError: UserErrorInfo | null;
  loading: boolean;
  error: UserErrorInfo | null;
  reload: () => void;
}

export function useSettings(): UseSettingsResult {
  const [snapshot, setSnapshot] = useState<EffectiveSettingsSnapshot | null>(null);
  const [runtime, setRuntime] = useState<DesktopRuntimeInfo | null>(null);
  const [sidecarState, setSidecarState] = useState<SidecarState | null>(null);
  const [runtimeError, setRuntimeError] = useState<UserErrorInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<UserErrorInfo | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const reload = useCallback(() => setReloadKey((value) => value + 1), []);

  useEffect(() => {
    let active = true;
    const bridge = getDesktopBridge();
    const unsubscribe = bridge?.onBackendState((state) => {
      if (active) setSidecarState(state);
    });

    setLoading(true);
    setError(null);
    setRuntimeError(null);
    Promise.allSettled([settingsApi.get(), getDesktopRuntime()])
      .then(([settingsResult, runtimeResult]) => {
        if (!active) return;
        if (settingsResult.status === "fulfilled") {
          setSnapshot(settingsResult.value.data);
        } else {
          setError(toUserError(settingsResult.reason, "无法加载当前设置，请检查服务状态后重试。"));
        }
        if (runtimeResult.status === "fulfilled") {
          const runtimeInfo = runtimeResult.value;
          setRuntime(runtimeInfo);
          setSidecarState((current) => current ?? (runtimeInfo ? { status: "ready", baseUrl: runtimeInfo.apiBaseUrl, pid: 0 } : null));
        } else {
          setRuntimeError(toUserError(runtimeResult.reason, "桌面运行时信息暂不可用，部分本地能力已受限。"));
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
      unsubscribe?.();
    };
  }, [reloadKey]);

  return { snapshot, runtime, sidecarState, runtimeError, loading, error, reload };
}
