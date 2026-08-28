import type { EffectiveSettingsSnapshot } from "../../types/settings";
import SectionCard from "./SectionCard";
import SecretField from "./SecretField";

interface GitHostSettingsProps {
  snapshot: EffectiveSettingsSnapshot;
  onChanged: () => void;
}

export default function GitHostSettings({ snapshot, onChanged }: GitHostSettingsProps) {
  return (
    <SectionCard title="代码托管" description="管理 GitHub 和 Gitee 的访问凭据，用于访问需要授权的仓库和接口。">
      <div className="pt-1">
        <SecretField label="GitHub Token" provider="github" state={snapshot.secret_status.github_token} description="只显示凭据状态，不会回显 Token。" onChanged={onChanged} />
        <SecretField label="Gitee Token" provider="gitee" state={snapshot.secret_status.gitee_token} description="只显示凭据状态，不会回显 Token。" onChanged={onChanged} />
      </div>
    </SectionCard>
  );
}
