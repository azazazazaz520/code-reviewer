import type { EffectiveSettingsSnapshot } from "../../types/settings";
import SectionCard from "./SectionCard";
import SecretField from "./SecretField";

interface GitHostSettingsProps {
  snapshot: EffectiveSettingsSnapshot;
}

export default function GitHostSettings({ snapshot }: GitHostSettingsProps) {
  return (
    <SectionCard title="代码托管" description="查看当前 Git 主机凭据状态。连接测试和凭据管理将在后续阶段提供。">
      <div className="pt-1">
        <div className="flex items-start gap-3 border-b border-border/70 py-4">
          <div>
            <div className="text-sm font-medium">连接状态</div>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">P0 不主动请求远程主机，不将未验证状态显示为连接成功。</p>
          </div>
          <span className="ml-auto shrink-0 text-sm text-muted-foreground">未测试</span>
        </div>
        <SecretField label="GitHub Token" state={snapshot.secret_status.github_token} description="仅展示是否存在有效配置，不回显 Token。" />
        <SecretField label="Gitee Token" state={snapshot.secret_status.gitee_token} description="仅展示是否存在有效配置，不回显 Token。" />
      </div>
    </SectionCard>
  );
}
