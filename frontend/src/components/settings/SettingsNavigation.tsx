import {
  Database,
  GitBranch,
  Info,
  Palette,
  Settings2,
  SlidersHorizontal,
  Sparkles,
} from "lucide-react";
import type { SettingsSection } from "../../types/settings";

export const settingsSections: Array<{
  id: SettingsSection;
  label: string;
  description: string;
  icon: typeof Palette;
}> = [
  { id: "appearance", label: "常规与外观", description: "主题与界面偏好", icon: Palette },
  { id: "model", label: "模型服务", description: "当前模型与凭据状态", icon: Sparkles },
  { id: "git", label: "代码托管", description: "GitHub 与 Gitee 状态", icon: GitBranch },
  { id: "review", label: "审查行为", description: "上下文与审查策略", icon: SlidersHorizontal },
  { id: "prompt", label: "提示词工作台", description: "请求与会话限制", icon: Settings2 },
  { id: "storage", label: "数据与诊断", description: "路径与运行状态", icon: Database },
  { id: "about", label: "关于", description: "版本与运行信息", icon: Info },
];

interface SettingsNavigationProps {
  activeSection: SettingsSection;
  onChange: (section: SettingsSection) => void;
}

export default function SettingsNavigation({ activeSection, onChange }: SettingsNavigationProps) {
  return (
    <nav className="space-y-2" aria-label="设置分区导航">
      <label className="sr-only" htmlFor="settings-section-select">
        设置分区
      </label>
      <select
        id="settings-section-select"
        className="flex h-11 w-full rounded-lg border border-input bg-background px-3 text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 md:hidden"
        value={activeSection}
        onChange={(event) => onChange(event.target.value as SettingsSection)}
      >
        {settingsSections.map((section) => (
          <option key={section.id} value={section.id}>
            {section.label}
          </option>
        ))}
      </select>

      <div className="hidden md:block">
        {settingsSections.map((section) => {
          const Icon = section.icon;
          const active = section.id === activeSection;
          return (
            <button
              key={section.id}
              type="button"
              className={`flex min-h-12 w-full items-center gap-3 rounded-lg px-3 py-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/30 ${
                active
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              }`}
              onClick={() => onChange(section.id)}
              aria-current={active ? "page" : undefined}
            >
              <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium">{section.label}</span>
                <span className="block truncate text-xs opacity-75">{section.description}</span>
              </span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
