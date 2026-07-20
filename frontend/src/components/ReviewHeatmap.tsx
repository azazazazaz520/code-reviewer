import type { HeatmapData, HeatmapRepoRow } from "../types";

const monthLabel = (month: string) => {
  const [, m] = month.split("-");
  return `${parseInt(m, 10)}月`;
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
                    <div
                      onClick={() =>
                        cell.review_count > 0 &&
                        onCellClick(repo.repo_id, month)
                      }
                      title={
                        cell.review_count > 0
                          ? `${repo.repo_name} — ${cell.month}\n审查 ${cell.review_count} 次 · 最高风险: ${cell.worst_risk ?? "—"}`
                          : `${repo.repo_name} — ${cell.month}\n无审查`
                      }
                      style={{
                        width: 36,
                        height: 36,
                        backgroundColor: bg,
                        opacity: cell.review_count > 0 ? 1 : 0.4,
                        cursor: cell.review_count > 0 ? "pointer" : "default",
                        borderRadius: 4,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        fontSize: 11,
                        color: cell.worst_risk ? "#fff" : "var(--muted-foreground)",
                        fontWeight: 600,
                        margin: "0 auto",
                        transition: "transform 0.15s",
                      }}
                      onMouseEnter={(e) => {
                        (e.currentTarget as HTMLElement).style.transform = "scale(1.15)";
                      }}
                      onMouseLeave={(e) => {
                        (e.currentTarget as HTMLElement).style.transform = "scale(1)";
                      }}
                    >
                      {cell.review_count > 0 ? cell.review_count : ""}
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="flex items-center gap-2 mt-3 text-xs text-muted-foreground">
        <span>少</span>
        <span className="w-3 h-3 rounded-sm bg-muted opacity-40" />
        <span className="w-3 h-3 rounded-sm bg-severity-low" />
        <span className="w-3 h-3 rounded-sm bg-severity-medium" />
        <span className="w-3 h-3 rounded-sm bg-severity-high" />
        <span className="w-3 h-3 rounded-sm bg-severity-critical" />
        <span>多</span>
      </div>
    </div>
  );
}
