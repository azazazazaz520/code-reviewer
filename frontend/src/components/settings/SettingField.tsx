interface SettingFieldProps {
  label: string;
  value: React.ReactNode;
  description?: string;
  source?: string;
}

export default function SettingField({ label, value, description, source }: SettingFieldProps) {
  return (
    <div className="grid gap-1.5 border-b border-border/70 py-4 last:border-b-0 sm:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] sm:gap-6">
      <div>
        <div className="text-sm font-medium">{label}</div>
        {description && <p className="mt-1 text-xs leading-5 text-muted-foreground">{description}</p>}
      </div>
      <div className="min-w-0 text-sm text-foreground sm:text-right">
        <div className="break-words font-mono text-xs sm:text-sm">{value}</div>
        {source && <div className="mt-1 text-xs text-muted-foreground">来源：{source}</div>}
      </div>
    </div>
  );
}
