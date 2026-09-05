import { Cell, Pie, PieChart } from "recharts";

type Severity = "critical" | "high" | "medium" | "low";

interface SeverityItem {
  key: Severity;
  label: string;
  count: number;
  colorClass: string;
  textClass: string;
  colorVariable: string;
}

interface RiskDistributionChartProps {
  bySeverity: Record<string, number>;
  totalFindings: number;
}

const severityItems: Array<Omit<SeverityItem, "count">> = [
  {
    key: "critical",
    label: "严重",
    colorClass: "bg-severity-critical",
    textClass: "text-severity-critical",
    colorVariable: "var(--severity-critical)",
  },
  {
    key: "high",
    label: "高危",
    colorClass: "bg-severity-high",
    textClass: "text-severity-high",
    colorVariable: "var(--severity-high)",
  },
  {
    key: "medium",
    label: "中危",
    colorClass: "bg-severity-medium",
    textClass: "text-severity-medium",
    colorVariable: "var(--severity-medium)",
  },
  {
    key: "low",
    label: "低危",
    colorClass: "bg-severity-low",
    textClass: "text-severity-low",
    colorVariable: "var(--severity-low)",
  },
];

function clampCount(value: number | undefined) {
  return Number.isFinite(value) && value && value > 0 ? value : 0;
}

function getPercentage(count: number, total: number) {
  return total === 0 ? 0 : Math.round((count / total) * 100);
}

export default function RiskDistributionChart({
  bySeverity,
  totalFindings,
}: RiskDistributionChartProps) {
  const items: SeverityItem[] = severityItems.map((item) => ({
    ...item,
    count: clampCount(bySeverity[item.key]),
  }));
  const classifiedTotal = items.reduce((sum, item) => sum + item.count, 0);
  const total = Math.max(clampCount(totalFindings), classifiedTotal);
  const dominantItem = [...items]
    .filter((item) => item.count > 0)
    .sort((left, right) => right.count - left.count)[0];
  const chartItems = items.filter((item) => item.count > 0);
  const ariaLabel = items
    .map((item) => `${item.label} ${item.count} 项`)
    .join("，");

  return (
    <section className="rounded-lg border bg-card p-4" aria-labelledby="risk-distribution-title">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 id="risk-distribution-title" className="text-sm font-medium">
            风险分布
          </h3>
          <p className="mt-1 text-xs text-muted-foreground">
            按严重度查看本次审查的问题构成
          </p>
        </div>
        <span className="rounded-full border px-2.5 py-1 text-xs text-muted-foreground">
          共 {total} 项风险
        </span>
      </div>

      <div className="mt-6 grid gap-6 md:grid-cols-[minmax(170px,0.55fr)_minmax(280px,1fr)] md:items-center">
        <div className="flex justify-center">
          <div
            className="relative h-44 w-44"
            role="img"
            aria-label={`风险分布：${ariaLabel}`}
          >
            {chartItems.length > 0 ? (
              <PieChart width={176} height={176}>
                <Pie
                  data={chartItems}
                  dataKey="count"
                  nameKey="label"
                  cx="50%"
                  cy="50%"
                  innerRadius={54}
                  outerRadius={78}
                  paddingAngle={1}
                  stroke="var(--card)"
                  strokeWidth={2}
                  isAnimationActive={false}
                >
                  {chartItems.map((item) => (
                    <Cell key={item.key} fill={item.colorVariable} />
                  ))}
                </Pie>
              </PieChart>
            ) : (
              <div className="absolute inset-0 rounded-full border-[18px] border-muted" />
            )}
            <div data-testid="risk-distribution-center" className="absolute inset-0 grid place-items-center">
              <div className="grid h-28 w-28 place-items-center rounded-full bg-card shadow-inner">
                <div className="text-center">
                  <div className="text-4xl font-semibold tracking-tight tabular-nums">{total}</div>
                  <div className="mt-1 text-xs text-muted-foreground">项问题</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="space-y-5">
          <div>
            <p className="text-sm font-medium">
              {dominantItem ? `风险主要集中在${dominantItem.label}级别` : "暂无风险发现"}
            </p>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">
              {dominantItem
                ? `${dominantItem.label}问题占全部发现的 ${getPercentage(dominantItem.count, total)}%。`
                : "本次审查未发现需要展示的风险问题。"}
            </p>
          </div>

          <div className="grid gap-x-8 gap-y-2 sm:grid-cols-2" aria-label="风险等级明细">
            {items.map((item) => (
              <div
                key={item.key}
                className={`flex items-center justify-between gap-3 ${item.count === 0 ? "opacity-55" : ""}`}
              >
                <span className="flex min-w-0 items-center gap-2 text-sm text-muted-foreground">
                  <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${item.colorClass}`} />
                  <span>{item.label}</span>
                </span>
                <span className="font-medium tabular-nums">
                  {item.count}
                  <span className="ml-1 text-xs font-normal text-muted-foreground">
                    ({getPercentage(item.count, total)}%)
                  </span>
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
