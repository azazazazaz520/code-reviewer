import { Layout as AntLayout, Menu } from "antd";
import { DashboardOutlined, GithubOutlined } from "@ant-design/icons";
import { Outlet, useNavigate, useLocation } from "react-router-dom";

const { Sider } = AntLayout;

export default function Layout() {
  const navigate = useNavigate();
  const location = useLocation();

  const items = [
    { key: "/", icon: <DashboardOutlined />, label: "仪表盘" },
    { key: "/repos", icon: <GithubOutlined />, label: "仓库管理" },
  ];

  return (
    <div style={{ display: "flex", minHeight: "100vh" }}>
      <AntLayout hasSider style={{ flex: "0 0 auto", background: "transparent" }}>
        <Sider
          collapsible
          style={{ height: "100vh", position: "sticky", top: 0 }}
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
      </AntLayout>

      <main
        style={{
          flex: 1,
          minWidth: 0,
          padding: 24,
          background: "var(--background)",
          overflow: "auto",
        }}
      >
        <Outlet />
      </main>
    </div>
  );
}
