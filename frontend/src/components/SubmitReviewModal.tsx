import { useEffect, useState } from "react";
import {
  Modal,
  Select,
  Radio,
  List,
  Button,
  Input,
  InputNumber,
  Space,
  Typography,
  message,
  Spin,
  Alert,
} from "antd";
import { useNavigate } from "react-router-dom";
import type { PRItem, CommitItem, Repo } from "../types";
import { repoApi } from "../api/repos";
import { reviewApi } from "../api/reviews";

interface Props {
  open: boolean;
  onClose: () => void;
  preSelectedRepoId?: string;
}

export default function SubmitReviewModal({ open, onClose, preSelectedRepoId }: Props) {
  const navigate = useNavigate();
  const [repos, setRepos] = useState<Repo[]>([]);
  const [repoId, setRepoId] = useState<string | null>(preSelectedRepoId ?? null);
  const [reviewType, setReviewType] = useState<"pr" | "local">("pr");
  const [selectedPR, setSelectedPR] = useState<PRItem | null>(null);
  const [selectedCommit, setSelectedCommit] = useState<CommitItem | null>(null);
  const [prs, setPRs] = useState<PRItem[]>([]);
  const [commits, setCommits] = useState<CommitItem[]>([]);
  const [loadingList, setLoadingList] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  // 降级模式：列表加载失败时允许手动输入
  const [manualPR, setManualPR] = useState<number | null>(null);
  const [manualCommit, setManualCommit] = useState<string>("");

  // 加载仓库列表
  useEffect(() => {
    if (open) {
      repoApi.list().then((res) => setRepos(res.data)).catch(() => setRepos([]));
    }
  }, [open]);

  // 预设仓库
  useEffect(() => {
    if (preSelectedRepoId) {
      setRepoId(preSelectedRepoId);
    }
  }, [preSelectedRepoId]);

  // 切换仓库或审查类型时加载列表
  useEffect(() => {
    if (!repoId) {
      setPRs([]);
      setCommits([]);
      setListError(null);
      return;
    }

    setLoadingList(true);
    setListError(null);
    setSelectedPR(null);
    setSelectedCommit(null);

    if (reviewType === "pr") {
      reviewApi
        .listPRs(repoId)
        .then((res) => {
          setPRs(res.data);
          setListError(null);
        })
        .catch((err) => {
          setPRs([]);
          const msg = err?.response?.data?.detail || "无法加载 PR 列表";
          setListError(msg);
        })
        .finally(() => setLoadingList(false));
    } else {
      reviewApi
        .listCommits(repoId)
        .then((res) => {
          setCommits(res.data);
          setListError(null);
        })
        .catch((err) => {
          setCommits([]);
          const msg = err?.response?.data?.detail || "无法加载 Commit 列表";
          setListError(msg);
        })
        .finally(() => setLoadingList(false));
    }
  }, [repoId, reviewType]);

  const handleSubmit = async () => {
    if (!repoId) {
      message.warning("请选择仓库");
      return;
    }

    const prNumber = selectedPR ? selectedPR.number : manualPR;
    const commitHash = selectedCommit ? selectedCommit.hash : (manualCommit || undefined);

    if (reviewType === "pr" && !prNumber) {
      message.warning("请选择或输入 PR 编号");
      return;
    }

    setSubmitting(true);
    try {
      const res = await reviewApi.submit(repoId, {
        review_type: reviewType,
        pr_number: prNumber ?? undefined,
        commit_hash: commitHash || undefined,
      });
      message.success("审查已提交");
      onClose();
      resetForm();
      navigate(`/reviews/${res.data.id}`);
    } catch {
      message.error("提交审查失败");
    } finally {
      setSubmitting(false);
    }
  };

  const resetForm = () => {
    setSelectedPR(null);
    setSelectedCommit(null);
    setManualPR(null);
    setManualCommit("");
    setListError(null);
  };

  const handleClose = () => {
    resetForm();
    onClose();
  };

  const formatTimeAgo = (isoStr: string) => {
    const diff = Date.now() - new Date(isoStr).getTime();
    const hours = Math.floor(diff / 3600000);
    if (hours < 1) return "刚刚";
    if (hours < 24) return `${hours}h 前`;
    const days = Math.floor(hours / 24);
    if (days < 30) return `${days}d 前`;
    return new Date(isoStr).toLocaleDateString();
  };

  return (
    <Modal
      title="发起审查"
      open={open}
      onCancel={handleClose}
      footer={[
        <Button key="cancel" onClick={handleClose}>取消</Button>,
        <Button key="submit" type="primary" loading={submitting} onClick={handleSubmit}>开始审查</Button>,
      ]}
      width={600}
      destroyOnClose
    >
      {/* 仓库选择 */}
      <div style={{ marginBottom: 16 }}>
        <Typography.Text strong style={{ display: "block", marginBottom: 4 }}>仓库</Typography.Text>
        <Select
          showSearch
          placeholder="选择仓库"
          value={repoId}
          onChange={(v) => setRepoId(v)}
          filterOption={(input, option) =>
            (option?.label as string)?.toLowerCase().includes(input.toLowerCase())
          }
          options={repos.map((r) => ({ label: r.name, value: r.id }))}
          style={{ width: "100%" }}
          status={!repoId ? "error" : undefined}
        />
      </div>

      {/* 审查类型 */}
      <div style={{ marginBottom: 16 }}>
        <Typography.Text strong style={{ display: "block", marginBottom: 4 }}>审查类型</Typography.Text>
        <Radio.Group
          value={reviewType}
          onChange={(e) => setReviewType(e.target.value)}
        >
          <Radio.Button value="pr">PR 审查</Radio.Button>
          <Radio.Button value="local">Local Commit</Radio.Button>
        </Radio.Group>
      </div>

      {/* 选择目标 */}
      <div style={{ marginBottom: 8 }}>
        <Typography.Text strong>
          {reviewType === "pr" ? "选择 PR" : "选择 Commit"}
        </Typography.Text>
      </div>

      {loadingList && (
        <div style={{ textAlign: "center", padding: 24 }}>
          <Spin tip="加载中..." />
        </div>
      )}

      {listError && (
        <div style={{ marginBottom: 12 }}>
          <Alert
            type="warning"
            message={listError}
            showIcon
            style={{ marginBottom: 8 }}
          />
          {reviewType === "pr" ? (
            <Space>
              <Typography.Text>手动输入 PR 编号：</Typography.Text>
              <InputNumber
                min={1}
                value={manualPR}
                onChange={(v) => setManualPR(v)}
                placeholder="PR 编号"
              />
            </Space>
          ) : (
            <Space>
              <Typography.Text>手动输入 Commit Hash：</Typography.Text>
              <Input
                value={manualCommit}
                onChange={(e) => setManualCommit(e.target.value)}
                placeholder="留空使用 HEAD"
              />
            </Space>
          )}
        </div>
      )}

      {!loadingList && !listError && reviewType === "pr" && (
        <List
          dataSource={prs}
          locale={{ emptyText: "该仓库暂无 Open PR" }}
          renderItem={(pr) => (
            <List.Item
              key={pr.number}
              onClick={() => setSelectedPR(pr)}
              style={{
                cursor: "pointer",
                padding: "8px 12px",
                borderRadius: 4,
                backgroundColor: selectedPR?.number === pr.number ? "#e6f4ff" : undefined,
                border: selectedPR?.number === pr.number ? "1px solid #1677ff" : "1px solid transparent",
              }}
            >
              <List.Item.Meta
                title={<span>#{pr.number} — {pr.title}</span>}
                description={`${pr.author} · ${formatTimeAgo(pr.created_at)}`}
              />
            </List.Item>
          )}
          style={{ maxHeight: 240, overflow: "auto", border: "1px solid #f0f0f0", borderRadius: 8 }}
        />
      )}

      {!loadingList && !listError && reviewType === "local" && (
        <List
          dataSource={commits}
          locale={{ emptyText: "该仓库无 Commit 记录" }}
          renderItem={(commit) => (
            <List.Item
              key={commit.hash}
              onClick={() => setSelectedCommit(commit)}
              style={{
                cursor: "pointer",
                padding: "8px 12px",
                borderRadius: 4,
                backgroundColor: selectedCommit?.hash === commit.hash ? "#e6f4ff" : undefined,
                border: selectedCommit?.hash === commit.hash ? "1px solid #1677ff" : "1px solid transparent",
              }}
            >
              <List.Item.Meta
                title={<span style={{ fontFamily: "monospace" }}>{commit.short_hash}</span>}
                description={`${commit.message} · ${commit.author} · ${formatTimeAgo(commit.date)}`}
              />
            </List.Item>
          )}
          style={{ maxHeight: 240, overflow: "auto", border: "1px solid #f0f0f0", borderRadius: 8 }}
        />
      )}
    </Modal>
  );
}
