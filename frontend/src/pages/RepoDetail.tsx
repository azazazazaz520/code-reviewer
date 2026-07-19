import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Radio,
  Space,
  Table,
  Tag,
  message,
} from "antd";
import type { Repo, ReviewTask } from "../types";
import { repoApi } from "../api/repos";
import { reviewApi } from "../api/reviews";

export default function RepoDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [repo, setRepo] = useState<Repo | null>(null);
  const [tasks, setTasks] = useState<ReviewTask[]>([]);
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);

  const load = async () => {
    if (!id) return;
    const [r, t] = await Promise.all([repoApi.get(id), reviewApi.list(id)]);
    setRepo(r.data);
    setTasks(t.data);
  };

  useEffect(() => {
    load();
  }, [id]);

  const handleSubmit = async () => {
    if (!id) return;
    try {
      const values = await form.validateFields();
      setLoading(true);
      await reviewApi.submit(id, values);
      message.success("审查已提交");
      form.resetFields();
      load();
    } catch {
      // validation
    } finally {
      setLoading(false);
    }
  };

  if (!repo) return <Card loading />;

  return (
    <>
      <Button onClick={() => navigate("/repos")} style={{ marginBottom: 16 }}>
        ← 返回
      </Button>
      <h2>{repo.name}</h2>
      <p>
        {repo.git_url} · 本地: {repo.local_path}
      </p>

      <Card title="提交审查" style={{ marginBottom: 24 }}>
        <Form form={form} layout="inline">
          <Form.Item name="review_type" label="类型" initialValue="local">
            <Radio.Group>
              <Radio value="local">Local Commit</Radio>
              <Radio value="pr">GitHub PR</Radio>
            </Radio.Group>
          </Form.Item>
          <Form.Item name="pr_number" label="PR 编号">
            <InputNumber min={1} />
          </Form.Item>
          <Form.Item name="commit_hash" label="Commit Hash">
            <Input placeholder="留空使用 HEAD" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" onClick={handleSubmit} loading={loading}>
              提交审查
            </Button>
          </Form.Item>
        </Form>
      </Card>

      <Card title="审查历史">
        <Table<ReviewTask>
          dataSource={tasks}
          rowKey="id"
          columns={[
            { title: "类型", dataIndex: "review_type", width: 80 },
            { title: "标识", dataIndex: "pr_number", width: 80 },
            {
              title: "状态",
              dataIndex: "status",
              width: 100,
              render: (s: string) => (
                <Tag color={s === "done" ? "green" : s === "failed" ? "red" : "blue"}>{s}</Tag>
              ),
            },
            {
              title: "时间",
              dataIndex: "created_at",
              render: (v: string) => new Date(v).toLocaleString(),
            },
            {
              title: "操作",
              render: (_: unknown, r: ReviewTask) =>
                r.status === "done" && (
                  <a onClick={() => navigate(`/reviews/${r.id}`)}>查看报告</a>
                ),
            },
          ]}
        />
      </Card>
    </>
  );
}
