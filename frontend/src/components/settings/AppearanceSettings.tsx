import { Monitor, Moon, Sun } from "lucide-react";
import { useThemeContext } from "../theme-provider";
import SectionCard from "./SectionCard";

const themes = [
  { value: "system" as const, label: "跟随系统", description: "根据操作系统的外观设置自动切换", icon: Monitor },
  { value: "light" as const, label: "浅色", description: "使用明亮的工作区背景", icon: Sun },
  { value: "dark" as const, label: "深色", description: "使用低亮度的工作区背景", icon: Moon },
];

export default function AppearanceSettings() {
  const { theme, setTheme } = useThemeContext();

  return (
    <SectionCard title="外观" description="选择设置页和审查工作区使用的主题。主题会立即生效并保存在本地浏览器偏好中。">
      <fieldset className="grid gap-3 pt-3 sm:grid-cols-3">
        <legend className="sr-only">主题</legend>
        {themes.map((item) => {
          const Icon = item.icon;
          const selected = theme === item.value;
          return (
            <label
              key={item.value}
              className={`flex min-h-24 cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors ${
                selected ? "border-primary bg-primary/5" : "border-border hover:bg-muted/60"
              }`}
            >
              <input
                type="radio"
                name="theme"
                value={item.value}
                checked={selected}
                onChange={() => setTheme(item.value)}
                className="mt-1 h-4 w-4 accent-primary"
              />
              <span>
                <span className="flex items-center gap-2 text-sm font-medium">
                  <Icon className="h-4 w-4" aria-hidden="true" />
                  {item.label}
                </span>
                <span className="mt-1 block text-xs leading-5 text-muted-foreground">{item.description}</span>
              </span>
            </label>
          );
        })}
      </fieldset>
    </SectionCard>
  );
}
