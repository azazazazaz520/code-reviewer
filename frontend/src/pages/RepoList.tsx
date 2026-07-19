import { useEffect, useState } from "react";
import { Button, Card, Form, Input, Modal, Space, Table, message } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import type { Repo } from "../types";
import { repoApi } from "../api/repos";

export default function RepoList() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();
  const navigate = useNavigate();

  const load = () => repoApi.list().then((res) => setRepos(res.data));

  useEffect(() => {
    load();
  }, []);

  const handleCreate = async () => {
    try {
      const values = await form.validateFields();
      await repoApi.create(values);
      message.success("仓库已添加");
      setOpen(false);
      form.resetFields();
      load();
    } catch {
      // validation failed
    }
  };

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <h2>仓库管理</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>
          添加仓库
        </Button>
      </div>

      <Table<Repo>
        dataSource={repos}
        rowKey="id"
        columns={[
          { title: "名称", dataIndex: "name" },
          { title: "Git URL", dataIndex: "git_url", ellipsis: true },
          { title: "本地路径", dataIndex: "local_path", ellipsis: true },
          { title: "默认分支", dataIndex: "default_branch", width: 100 },
          {
            title: "操作",
            width: 120,
            render: (_: unknown, r: Repo) => (
              <a onClick={() => navigate(`/repos/${r.id}`)}>详情</a>
            ),
          },
        ]}
      />

      <Modal title="添加仓库" open={open} onOk={handleCreate} onCancel={() => setOpen(false)}>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="git_url" label="Git URL" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="local_path" label="本地路径" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="default_branch" label="默认分支" initialValue="main">
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
