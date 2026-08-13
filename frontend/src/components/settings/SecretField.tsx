import { CheckCircle2, CircleSlash2 } from "lucide-react";
import type { SecretState } from "../../types/settings";

interface SecretFieldProps {
  label: string;
  state: SecretState;
  description: string;
}

export default function SecretField({ label, state, description }: SecretFieldProps) {
  const configured = state === "configured";
  return (
    <div className="flex items-start gap-3 border-b border-border/70 py-4 last:border-b-0">
      {configured ? (
        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
      ) : (
        <CircleSlash2 className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      )}
      <div className="min-w-0">
        <div className="text-sm font-medium">{label}</div>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">{description}</p>
      </div>
      <span className="ml-auto shrink-0 text-sm text-muted-foreground">
        {configured ? "已配置" : "未配置"}
      </span>
    </div>
  );
}
