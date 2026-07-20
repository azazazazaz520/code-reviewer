import { Layout, Menu } from "antd";
import { DashboardOutlined, GithubOutlined } from "@ant-design/icons";
import { Outlet, useNavigate, useLocation } from "react-router-dom";

const { Sider } = Layout;

export default function AppLayout() {
  const navigate = useNavigate();
  const location = useLocation();

  const items = [
    { key: "/", icon: <DashboardOutlined />, label: "仪表盘" },
    { key: "/repos", icon: <GithubOutlined />, label: "仓库管理" },
  ];

  return (
    <Layout
      hasSider
      style={{ minHeight: "100vh", background: "var(--background)" }}
    >
      <Sider
        collapsible
        style={{ position: "sticky", top: 0, height: "100vh", overflow: "auto" }}
      >
        <div
          style={{
            height: 48,
            margin: 16,
            color: "#fff",
            fontSize: 18,
            fontWeight: 700,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          Code Reviewer
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={items}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>

      <main
        style={{
          flex: 1,
          minWidth: 0,
          padding: 24,
          overflow: "auto",
          background: "var(--background)",
        }}
      >
        <Outlet />
      </main>
    </Layout>
  );
}
