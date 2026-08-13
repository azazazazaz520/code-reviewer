import { useCallback, useEffect, useState } from "react";
import { Archive, Plus } from "lucide-react";
import type { OverviewStats, ReviewTask, HeatmapData } from "../types";
import { statsApi } from "../api/stats";
import { reviewApi } from "../api/reviews";
import { useNavigate } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Skeleton } from "../components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../components/ui/table";
import ReviewHeatmap from "../components/ReviewHeatmap";
import SubmitReviewModal from "../components/SubmitReviewModal";
import ErrorNotice from "../components/ErrorNotice";
import { toUserError, type UserErrorInfo } from "../utils/error-message";

const riskBadge: Record<string, "critical" | "high" | "medium" | "low"> = {
  low: "low",
  medium: "medium",
  high: "high",
  critical: "critical",
};

const statusLabel: Record<string, string> = {
  pending: "等待中",
  running: "进行中",
  preparing: "准备中",
  done: "完成",
  failed: "失败",
};

export default function Dashboard() {
  const [stats, setStats] = useState<OverviewStats | null>(null);
  const [heatmap, setHeatmap] = useState<HeatmapData | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const navigate = useNavigate();

  const [statsError, setStatsError] = useState<UserErrorInfo | null>(null);
  const [heatmapError, setHeatmapError] = useState<UserErrorInfo | null>(null);
  const [statsLoading, setStatsLoading] = useState(true);
  const [actionPendingId, setActionPendingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<UserErrorInfo | null>(null);

  const loadStats = useCallback(async () => {
    setStatsLoading(true);
    setStatsError(null);
    try {
      const res = await statsApi.overview();
      setStats(res.data);
    } catch (error) {
      console.error("Failed to load dashboard stats:", error);
      setStatsError(toUserError(error, "无法加载仪表盘数据"));
    } finally {
      setStatsLoading(false);
    }
  }, []);

  const loadHeatmap = useCallback(async () => {
    setHeatmapError(null);
    try {
      const res = await statsApi.heatmap();
      setHeatmap(res.data);
    } catch (error) {
      setHeatmapError(toUserError(error, "无法加载审查活动数据"));
    }
  }, []);

  const handleArchive = async (review: ReviewTask) => {
    if (review.status === "pending" || review.status === "running") return;

    setActionPendingId(review.id);
    setActionError(null);
    try {
      await reviewApi.archive(review.id);
      await Promise.all([loadStats(), loadHeatmap()]);
    } catch (error) {
      setActionError(toUserError(error, "归档审查记录失败"));
    } finally {
      setActionPendingId(null);
    }
  };

  useEffect(() => {
    void loadStats();
    void loadHeatmap();
  }, [loadHeatmap, loadStats]);

  if (statsError && !stats) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-4">
        <ErrorNotice title="仪表盘加载失败" error={statsError} onRetry={() => void loadStats()} />
      </div>
    );
  }

  if (statsLoading || !stats) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <Skeleton className="h-8 w-24" />
          <Skeleton className="h-9 w-28" />
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
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
    const revision = r.head_revision || r.commit_hash;
    return revision ? revision.slice(0, 7) : "—";
  };

  const sourceLabel = (r: ReviewTask) => {
    if (r.source_type === "workspace") return "本地工作区";
    if (r.source_type === "remote_latest") return "远程最新提交";
    if (r.source_type === "remote_commit") return "远程 Commit";
    return r.review_type === "pr" ? "PR" : "远程 Commit";
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-bold tracking-tight">仪表盘</h1>
        <Button className="min-h-11 w-full sm:w-auto" onClick={() => setModalOpen(true)}>
          <Plus className="h-4 w-4 mr-1" />
          发起审查
        </Button>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
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
          {heatmapError ? (
            <ErrorNotice title="审查活动加载失败" error={heatmapError} onRetry={() => void loadHeatmap()} compact />
          ) : (
            <ReviewHeatmap
              data={heatmap}
              onCellClick={(repoId, month) =>
                navigate(`/repos/${repoId}?month=${encodeURIComponent(month)}`)
              }
            />
          )}
        </CardContent>
      </Card>

      {/* Recent reviews table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">最近审查</CardTitle>
        </CardHeader>
        {actionError && (
          <ErrorNotice error={actionError} compact className="mx-6 mb-3" />
        )}
        <CardContent className="p-0">
          <Table className="min-w-[760px]">
            <TableHeader>
              <TableRow>
                <TableHead className="px-6 py-3 text-muted-foreground">
                  仓库
                </TableHead>
                <TableHead className="px-6 py-3 text-muted-foreground">
                  类型
                </TableHead>
                <TableHead className="px-6 py-3 text-muted-foreground">
                  目标
                </TableHead>
                <TableHead className="px-6 py-3 text-muted-foreground">
                  风险/状态
                </TableHead>
                <TableHead className="px-6 py-3 text-muted-foreground">
                  时间
                </TableHead>
                <TableHead className="px-6 py-3 text-right text-muted-foreground">
                  操作
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {stats.recent_reviews.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="px-6 py-10 text-center text-muted-foreground">
                    暂无审查记录，点击“发起审查”开始
                  </TableCell>
                </TableRow>
              ) : stats.recent_reviews.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell className="px-6 py-3 max-w-[160px] truncate" title={r.repo_name}>
                      {r.repo_name}
                    </TableCell>
                    <TableCell className="px-6 py-3">
                      {sourceLabel(r)}
                    </TableCell>
                    <TableCell className="px-6 py-3">{formatTarget(r)}</TableCell>
                    <TableCell className="px-6 py-3">
                      {r.risk_level ? (
                        <Badge variant={riskBadge[r.risk_level]}>
                          {r.risk_level.toUpperCase()}
                        </Badge>
                      ) : r.status === "done" ? (
                        <span className="text-muted-foreground">—</span>
                      ) : (
                        <Badge variant="secondary">{statusLabel[r.status] || r.status}</Badge>
                      )}
                    </TableCell>
                    <TableCell className="px-6 py-3 text-muted-foreground">
                      {new Date(r.created_at).toLocaleString()}
                    </TableCell>
                    <TableCell className="px-6 py-3 text-right">
                      <div className="flex flex-wrap items-center justify-end gap-x-3 gap-y-1">
                        <Button
                          variant="link"
                          size="sm"
                          className="min-h-11 px-2 sm:min-h-0 sm:h-auto sm:p-0"
                          onClick={() => navigate(`/reviews/${r.id}`)}
                        >
                          查看详情
                        </Button>
                        <Button
                          variant="link"
                          size="sm"
                          className="min-h-11 px-2 sm:min-h-0 sm:h-auto sm:p-0"
                          disabled={actionPendingId === r.id || r.status === "pending" || r.status === "running"}
                          onClick={() => void handleArchive(r)}
                        >
                          <Archive className="mr-1 h-3.5 w-3.5" />
                          归档
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
            </TableBody>
          </Table>
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
