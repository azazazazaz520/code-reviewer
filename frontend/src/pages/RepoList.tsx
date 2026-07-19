import { useEffect, useState } from "react";
import { Button, Form, Input, Modal, Popconfirm, Space, Table, message } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import type { Repo } from "../types";
import { repoApi } from "../api/repos";

export default function RepoList() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Repo | null>(null);
  const [form] = Form.useForm();
  const navigate = useNavigate();

  const load = () => repoApi.list().then((res) => setRepos(res.data));

  useEffect(() => {
    load();
  }, []);

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      if (editing) {
        await repoApi.update(editing.id, values);
        message.success("仓库已更新");
      } else {
        await repoApi.create(values);
        message.success("仓库已添加");
      }
      setOpen(false);
      setEditing(null);
      form.resetFields();
      load();
    } catch {
      // validation
    }
  };

  const handleEdit = (repo: Repo) => {
    setEditing(repo);
    form.setFieldsValue(repo);
    setOpen(true);
  };

  const handleDelete = async (id: string) => {
    await repoApi.remove(id);
    message.success("仓库已删除");
    load();
  };

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <h2>仓库管理</h2>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => {
            setEditing(null);
            form.resetFields();
            setOpen(true);
          }}
        >
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
            width: 200,
            render: (_: unknown, r: Repo) => (
              <Space>
                <a onClick={() => navigate(`/repos/${r.id}`)}>详情</a>
                <a onClick={() => handleEdit(r)}>编辑</a>
                <Popconfirm title="确定删除此仓库？关联的审查记录也会被删除" onConfirm={() => handleDelete(r.id)}>
                  <a style={{ color: "red" }}>删除</a>
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />

      <Modal
        title={editing ? "编辑仓库" : "添加仓库"}
        open={open}
        onOk={handleSave}
        onCancel={() => {
          setOpen(false);
          setEditing(null);
        }}
      >
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
