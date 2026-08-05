import type { HeatmapData, HeatmapRepoRow } from "../types";

const monthLabel = (month: string) => {
  const [year, m] = month.split("-");
  return `${year}年${parseInt(m, 10)}月`;
};

const severityVar = (risk: string | null) => {
  if (!risk) return undefined;
  return `var(--severity-${risk})`;
};

interface Props {
  data: HeatmapData | null;
  onCellClick: (repoId: string, month: string) => void;
}

export default function ReviewHeatmap({ data, onCellClick }: Props) {
  if (!data || data.repos.length === 0) {
    return (
      <div className="py-6 text-center text-muted-foreground">暂无审查数据</div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr>
            <th className="text-left font-medium text-muted-foreground px-2 py-1 w-36">
              仓库
            </th>
            {data.months.map((month) => (
              <th
                key={month}
                className="text-center font-medium text-muted-foreground px-1 py-1 w-14 text-xs"
              >
                {monthLabel(month)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.repos.map((repo: HeatmapRepoRow) => (
            <tr key={repo.repo_id}>
              <td className="px-2 py-1 truncate max-w-36" title={repo.repo_name}>
                {repo.repo_name}
              </td>
              {data.months.map((month) => {
                const cell = repo.cells.find((c) => c.month === month);
                if (!cell) return <td key={month} className="px-1 py-1" />;
                const bg = cell.worst_risk
                  ? severityVar(cell.worst_risk)
                  : "var(--muted)";
                return (
                  <td key={month} className="px-1 py-1">
                    <button
                      type="button"
                      onClick={() =>
                        cell.review_count > 0 &&
                        onCellClick(repo.repo_id, month)
                      }
                      disabled={cell.review_count === 0}
                      aria-label={
                        cell.review_count > 0
                          ? `${repo.repo_name}，${cell.month}，审查 ${cell.review_count} 次，最高风险 ${cell.worst_risk ?? "无"}`
                          : `${repo.repo_name}，${cell.month}，无审查`
                      }
                      title={
                        cell.review_count > 0
                          ? `${repo.repo_name} — ${cell.month}\n审查 ${cell.review_count} 次 · 最高风险: ${cell.worst_risk ?? "—"}`
                          : `${repo.repo_name} — ${cell.month}\n无审查`
                      }
                      className="mx-auto flex h-9 w-9 items-center justify-center rounded text-[11px] font-semibold transition-transform enabled:hover:scale-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-default"
                      style={{
                        backgroundColor: bg,
                        opacity: cell.review_count > 0 ? 1 : 0.4,
                        color: cell.worst_risk ? "#fff" : "var(--muted-foreground)",
                      }}
                    >
                      {cell.review_count > 0 ? cell.review_count : ""}
                    </button>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="flex flex-wrap items-center gap-2 mt-3 text-xs text-muted-foreground">
        <span>风险等级：</span>
        <span className="w-3 h-3 rounded-sm bg-muted opacity-40" />
        <span>无</span>
        <span className="w-3 h-3 rounded-sm bg-severity-low" />
        <span>低</span>
        <span className="w-3 h-3 rounded-sm bg-severity-medium" />
        <span>中</span>
        <span className="w-3 h-3 rounded-sm bg-severity-high" />
        <span>高</span>
        <span className="w-3 h-3 rounded-sm bg-severity-critical" />
        <span>严重</span>
      </div>
    </div>
  );
}
