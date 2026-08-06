import { useMemo, useState } from "react";
import { FileCode2 } from "lucide-react";
import type { ReviewChanges } from "../types";
import { Badge } from "./ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";

interface DiffFile {
  path: string;
  lines: string[];
  additions: number;
  deletions: number;
}

function parseDiff(changes: ReviewChanges): DiffFile[] {
  const rawDiff = changes.diff || "";
  const sections = rawDiff.split(/^diff --git /m).slice(1);

  if (sections.length === 0) {
    return changes.changed_files.map((path) => ({
      path,
      lines: [],
      additions: 0,
      deletions: 0,
    }));
  }

  return sections.map((section, index) => {
    const [header, ...rest] = section.split("\n");
    const pathMatch = header.match(/a\/(.+?) b\/(.+)$/);
    const path = pathMatch?.[2] || changes.changed_files[index] || "未知文件";
    const hunkStart = rest.findIndex((line) => line.startsWith("@@"));
    const lines = hunkStart >= 0 ? rest.slice(hunkStart) : rest;

    return {
      path,
      lines,
      additions: lines.filter((line) => line.startsWith("+") && !line.startsWith("+++"))
        .length,
      deletions: lines.filter((line) => line.startsWith("-") && !line.startsWith("---"))
        .length,
    };
  });
}

function revisionLabel(revision: string | null) {
  return revision ? revision.slice(0, 12) : "—";
}

function sourceLabel(changes: ReviewChanges) {
  if (changes.source_type === "workspace") return "本地工作区";
  if (changes.source_type === "remote_latest") return "远程最新提交";
  if (changes.source_type === "remote_commit") return "远程指定 Commit";
  return changes.review_type === "pr" ? `PR #${changes.pr_number ?? "—"}` : "远程 Commit";
}

export default function ChangeDiffViewer({ changes }: { changes: ReviewChanges }) {
  const files = useMemo(() => parseDiff(changes), [changes]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const selectedFile = files[selectedIndex] || files[0];
  const additions = files.reduce((total, file) => total + file.additions, 0);
  const deletions = files.reduce((total, file) => total + file.deletions, 0);

  if (!changes.diff && files.length === 0) return null;

  return (
    <Card>
      <CardHeader className="gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle className="text-base">提交变更</CardTitle>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <Badge variant="outline">{files.length} 个文件</Badge>
            <span className="text-severity-low">+{additions}</span>
            <span className="text-destructive">-{deletions}</span>
          </div>
        </div>
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span>{sourceLabel(changes)}</span>
          <span>基线 {revisionLabel(changes.base_revision)}</span>
          <span>提交 {revisionLabel(changes.head_revision || changes.commit_hash)}</span>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <div className="grid min-w-0 md:grid-cols-[240px_minmax(0,1fr)]">
          <nav className="border-b p-2 md:border-b-0 md:border-r" aria-label="变更文件">
            <div className="mb-1 px-2 py-1 text-xs font-medium text-muted-foreground">变更文件</div>
            <div className="space-y-1">
              {files.map((file, index) => (
                <button
                  key={`${file.path}-${index}`}
                  type="button"
                  className={`flex min-h-11 w-full items-center gap-2 rounded-md px-2 text-left text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                    selectedIndex === index ? "bg-muted font-medium" : "hover:bg-muted/60"
                  }`}
                  onClick={() => setSelectedIndex(index)}
                  aria-current={selectedIndex === index ? "true" : undefined}
                >
                  <FileCode2 className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <span className="min-w-0 flex-1 truncate" title={file.path}>{file.path}</span>
                  <span className="shrink-0 text-[11px]">
                    <span className="text-severity-low">+{file.additions}</span>{" "}
                    <span className="text-destructive">-{file.deletions}</span>
                  </span>
                </button>
              ))}
            </div>
          </nav>

          <section className="min-w-0" aria-label={selectedFile ? `${selectedFile.path} 的变更` : "代码变更"}>
            {selectedFile ? (
              <>
                <div className="border-b px-4 py-2 font-mono text-xs text-muted-foreground">{selectedFile.path}</div>
                <div className="max-h-[560px] overflow-auto bg-muted/20 font-mono text-xs leading-6">
                  {selectedFile.lines.length > 0 ? selectedFile.lines.map((line, index) => {
                    const isAddition = line.startsWith("+") && !line.startsWith("+++");
                    const isDeletion = line.startsWith("-") && !line.startsWith("---");
                    const isHunk = line.startsWith("@@");
                    return (
                      <div
                        key={`${index}-${line}`}
                        className={`grid min-w-max grid-cols-[3rem_minmax(0,1fr)] px-3 ${
                          isAddition
                            ? "bg-severity-low/10 text-severity-low"
                            : isDeletion
                              ? "bg-destructive/10 text-destructive"
                              : isHunk
                                ? "bg-primary/5 text-primary"
                                : "text-foreground/80"
                        }`}
                      >
                        <span className="select-none pr-3 text-right text-muted-foreground">{index + 1}</span>
                        <span className="whitespace-pre">{line || " "}</span>
                      </div>
                    );
                  }) : (
                    <div className="p-4 text-muted-foreground">该文件没有可显示的文本差异。</div>
                  )}
                </div>
              </>
            ) : (
              <div className="p-6 text-sm text-muted-foreground">该记录未保存变更内容。</div>
            )}
          </section>
        </div>
      </CardContent>
    </Card>
  );
}
