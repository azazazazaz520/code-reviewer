import {
  CircleAlert,
  TriangleAlert,
  AlertTriangle,
  Info,
  type LucideIcon,
} from "lucide-react";

export interface SeverityConfig {
  label: string;
  badgeVariant: "critical" | "high" | "medium" | "low";
  borderColor: string;
  icon: LucideIcon;
}

export const severityConfigMap: Record<string, SeverityConfig> = {
  critical: {
    label: "严重",
    badgeVariant: "critical",
    borderColor: "border-l-severity-critical",
    icon: CircleAlert,
  },
  high: {
    label: "高危",
    badgeVariant: "high",
    borderColor: "border-l-severity-high",
    icon: TriangleAlert,
  },
  medium: {
    label: "中危",
    badgeVariant: "medium",
    borderColor: "border-l-severity-medium",
    icon: AlertTriangle,
  },
  low: {
    label: "低危",
    badgeVariant: "low",
    borderColor: "border-l-severity-low",
    icon: Info,
  },
};

export function getSeverityConfig(severity: string): SeverityConfig {
  return severityConfigMap[severity] ?? severityConfigMap.low;
}
