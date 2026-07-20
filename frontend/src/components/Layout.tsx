import { Layout as AntLayout, Menu } from "antd";
import { DashboardOutlined, GithubOutlined } from "@ant-design/icons";
import { Outlet, useNavigate, useLocation } from "react-router-dom";

const { Sider, Content } = AntLayout;

export default function Layout() {
  const navigate = useNavigate();
  const location = useLocation();

  const items = [
    { key: "/", icon: <DashboardOutlined />, label: "仪表盘" },
    { key: "/repos", icon: <GithubOutlined />, label: "仓库管理" },
  ];

  return (
    <AntLayout style={{ minHeight: "100vh" }}>
      <Sider collapsible>
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
      <AntLayout>
        <Content
          style={{ margin: 24, padding: 24, background: "var(--background)" }}
        >
          <Outlet />
        </Content>
      </AntLayout>
    </AntLayout>
  );
}
