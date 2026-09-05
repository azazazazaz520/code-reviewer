import { useState } from "react";
import { Outlet, useNavigate, useLocation } from "react-router-dom";
import {
  LayoutDashboard,
  GitBranch,
  Menu,
  PanelLeftClose,
  PanelLeft,
  X,
  WandSparkles,
  Settings as SettingsIcon,
} from "lucide-react";
import { Button } from "./ui/button";
import { Modal } from "./ui/modal";

const navItems = [
  { path: "/", icon: LayoutDashboard, label: "仪表盘" },
  { path: "/repos", icon: GitBranch, label: "仓库管理" },
  { path: "/prompts", icon: WandSparkles, label: "Prompt 工具箱" },
  { path: "/settings", icon: SettingsIcon, label: "设置" },
];

export default function AppLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  const navigateTo = (path: string) => {
    navigate(path);
    setMobileOpen(false);
  };

  const isActive = (path: string) =>
    path === "/" ? location.pathname === "/" : location.pathname.startsWith(path);

  const NavContent = ({ compact = false }: { compact?: boolean }) => (
    <>
      <div className="flex items-center gap-2 h-12 px-4 border-b">
        {!compact && (
          <span className="font-bold text-sm truncate">Code Reviewer</span>
        )}
        {compact ? (
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 mx-auto"
            onClick={() => setCollapsed(false)}
            aria-label="展开侧边栏"
          >
            <PanelLeft className="h-4 w-4" />
          </Button>
        ) : (
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 ml-auto hidden md:inline-flex"
            onClick={() => setCollapsed(true)}
            aria-label="折叠侧边栏"
          >
            <PanelLeftClose className="h-4 w-4" />
          </Button>
        )}
      </div>

      <nav className="min-h-0 flex-1 overflow-y-auto p-2 space-y-1" aria-label="主导航">
        {navItems.map((item) => {
          const Icon = item.icon;
          const active = isActive(item.path);
          return (
            <button
              key={item.path}
              type="button"
              onClick={() => navigateTo(item.path)}
              className={`flex items-center gap-3 w-full rounded-md px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                active
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              } ${compact ? "justify-center px-2" : ""}`}
              title={compact ? item.label : undefined}
              aria-current={active ? "page" : undefined}
            >
              <Icon className="h-5 w-5 shrink-0" />
              {!compact && <span className="truncate">{item.label}</span>}
            </button>
          );
        })}
      </nav>

      {!compact && (
        <div className="p-3 border-t text-xs text-muted-foreground">
          Code Review Agent
        </div>
      )}
    </>
  );

  return (
    <div className="min-h-screen bg-background md:flex md:h-screen md:overflow-hidden">
      <header className="sticky top-0 z-30 flex h-12 items-center gap-3 border-b bg-background/95 px-4 backdrop-blur md:hidden">
        <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 min-h-11 min-w-11"
          onClick={() => setMobileOpen(true)}
          aria-label="打开导航"
        >
          <Menu className="h-4 w-4" />
        </Button>
        <span className="font-bold text-sm">Code Reviewer</span>
      </header>

      <aside
        className={`hidden h-full shrink-0 overflow-hidden md:flex flex-col bg-card border-r transition-all duration-200 ${
          collapsed ? "w-16" : "w-56"
        }`}
      >
        <NavContent compact={collapsed} />
      </aside>

      <Modal
        open={mobileOpen}
        onClose={() => setMobileOpen(false)}
        titleId="mobile-navigation-title"
        motion="drawer"
        overlayClassName="items-stretch justify-start p-0 md:hidden"
        panelClassName="relative flex h-full max-h-none w-72 max-w-[85vw] flex-col overflow-hidden rounded-none border-y-0 border-l-0 p-0"
      >
            <h2 id="mobile-navigation-title" className="sr-only">主导航</h2>
            <div className="flex items-center gap-2 h-12 px-4 border-b">
              <span className="font-bold text-sm truncate">Code Reviewer</span>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 min-h-11 min-w-11 ml-auto"
                onClick={() => setMobileOpen(false)}
                aria-label="关闭导航"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
            <nav className="flex-1 p-2 space-y-1" aria-label="移动端主导航">
              {navItems.map((item) => {
                const Icon = item.icon;
                const active = isActive(item.path);
                return (
                  <button
                    key={item.path}
                    type="button"
                    onClick={() => navigateTo(item.path)}
                    className={`flex items-center gap-3 w-full rounded-md px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                      active
                        ? "bg-primary/10 text-primary"
                        : "text-muted-foreground hover:bg-muted hover:text-foreground"
                    }`}
                    aria-current={active ? "page" : undefined}
                  >
                    <Icon className="h-5 w-5 shrink-0" />
                    <span className="truncate">{item.label}</span>
                  </button>
                );
              })}
            </nav>
      </Modal>

      <main data-app-background className="flex-1 min-w-0 md:h-full md:min-h-0 md:overflow-x-hidden md:overflow-y-auto">
        <div className="mx-auto w-full max-w-7xl p-4 sm:p-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
