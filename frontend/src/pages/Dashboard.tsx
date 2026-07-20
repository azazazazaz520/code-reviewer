import { useEffect, useState } from "react";
import { Plus } from "lucide-react";
import type { OverviewStats, ReviewTask, HeatmapData } from "../types";
import { statsApi } from "../api/stats";
import { useNavigate } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Skeleton } from "../components/ui/skeleton";
import ReviewHeatmap from "../components/ReviewHeatmap";
import SubmitReviewModal from "../components/SubmitReviewModal";

const riskBadge: Record<string, "critical" | "high" | "medium" | "low"> = {
  low: "low",
  medium: "medium",
  high: "high",
  critical: "critical",
};

const statusLabel: Record<string, string> = {
  pending: "等待中",
  running: "进行中",
  done: "完成",
  failed: "失败",
};

export default function Dashboard() {
  const [stats, setStats] = useState<OverviewStats | null>(null);
  const [heatmap, setHeatmap] = useState<HeatmapData | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    statsApi.overview().then((res) => setStats(res.data));
    statsApi.heatmap().then((res) => setHeatmap(res.data)).catch(() => {});
  }, []);

  if (!stats) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <Skeleton className="h-8 w-24" />
          <Skeleton className="h-9 w-28" />
        </div>
        <div className="grid grid-cols-3 gap-4">
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
        </div>
        <Skeleton className="h-48" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  const formatTarget = (r: ReviewTask) => {
    if (r.review_type === "pr") {
      return r.pr_number ? `#${r.pr_number}` : "—";
    }
    return r.commit_hash ? r.commit_hash.slice(0, 7) : "—";
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">仪表盘</h1>
        <Button onClick={() => setModalOpen(true)}>
          <Plus className="h-4 w-4 mr-1" />
          发起审查
        </Button>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-3 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="text-3xl font-bold">{stats.total_reviews}</div>
            <div className="text-sm text-muted-foreground mt-1">总审查次数</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-3xl font-bold">{stats.reviews_this_month}</div>
            <div className="text-sm text-muted-foreground mt-1">本月审查</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-3xl font-bold">{stats.active_repos}</div>
            <div className="text-sm text-muted-foreground mt-1">活跃仓库</div>
          </CardContent>
        </Card>
      </div>

      {/* Heatmap */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">审查活动热力图</CardTitle>
        </CardHeader>
        <CardContent>
          <ReviewHeatmap
            data={heatmap}
            onCellClick={(repoId) => navigate(`/repos/${repoId}`)}
          />
        </CardContent>
      </Card>

      {/* Recent reviews table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">最近审查</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b">
                <th className="text-left font-medium text-muted-foreground px-6 py-3">
                  仓库
                </th>
                <th className="text-left font-medium text-muted-foreground px-6 py-3">
                  类型
                </th>
                <th className="text-left font-medium text-muted-foreground px-6 py-3">
                  目标
                </th>
                <th className="text-left font-medium text-muted-foreground px-6 py-3">
                  风险/状态
                </th>
                <th className="text-left font-medium text-muted-foreground px-6 py-3">
                  时间
                </th>
                <th className="text-right font-medium text-muted-foreground px-6 py-3">
                  操作
                </th>
              </tr>
            </thead>
            <tbody>
              {stats.recent_reviews.map((r) => (
                <tr key={r.id} className="border-b last:border-0 hover:bg-muted/50">
                  <td className="px-6 py-3 max-w-[120px] truncate" title={r.repo_name}>
                    {r.repo_name}
                  </td>
                  <td className="px-6 py-3">
                    {r.review_type === "pr" ? "PR" : "Local"}
                  </td>
                  <td className="px-6 py-3">{formatTarget(r)}</td>
                  <td className="px-6 py-3">
                    {r.risk_level ? (
                      <Badge variant={riskBadge[r.risk_level]}>
                        {r.risk_level.toUpperCase()}
                      </Badge>
                    ) : r.status === "done" ? (
                      <span className="text-muted-foreground">—</span>
                    ) : (
                      <Badge variant="secondary">{statusLabel[r.status] || r.status}</Badge>
                    )}
                  </td>
                  <td className="px-6 py-3 text-muted-foreground">
                    {new Date(r.created_at).toLocaleString()}
                  </td>
                  <td className="px-6 py-3 text-right">
                    <Button
                      variant="link"
                      size="sm"
                      className="h-auto p-0"
                      onClick={() => navigate(`/reviews/${r.id}`)}
                    >
                      查看报告
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      {/* Risk distribution */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">风险分布</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            {Object.entries(stats.risk_distribution).map(([level, count]) => (
              <Badge key={level} variant={riskBadge[level] || "secondary"}>
                {level}: {count as number}
              </Badge>
            ))}
            {Object.values(stats.risk_distribution).every((v) => v === 0) && (
              <span className="text-muted-foreground">暂无数据</span>
            )}
          </div>
        </CardContent>
      </Card>

      <SubmitReviewModal open={modalOpen} onClose={() => setModalOpen(false)} />
    </div>
  );
}
