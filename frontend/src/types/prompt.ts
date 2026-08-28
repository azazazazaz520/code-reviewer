export type PromptPersona =
  | "general"
  | "frontend"
  | "backend"
  | "ui"
  | "qa"
  | "architecture";

export type PromptMode = "instant" | "review";
export type PromptClassificationType =
  | "bug"
  | "feature"
  | "ux"
  | "architecture"
  | "unknown";

export interface PromptOptimizeRequest {
  content: string;
  persona: PromptPersona;
  mode: PromptMode;
  glossary_enabled: boolean;
  idempotency_key?: string;
}
export interface PromptClassification {
  type: PromptClassificationType;
  confidence: number;
  reason: string;
}

export interface PromptTermMapping {
  original: string;
  professional: string;
  reason: string;
}

export interface PromptResult {
  classification: PromptClassification;
  problem_phenomenon: string;
  technical_essence: string;
  solution: string[];
  bug_view: string;
  prd_view: string;
  team_message: string;
  term_mappings: PromptTermMapping[];
  assumptions: string[];
  checks: string[];
}

export interface PromptOptimizeResponse {
  result: PromptResult;
  turn: number;
  max_turns: number;
  session_id: string | null;
  expires_at: string | null;
  metadata: PromptGenerationMetadata;
  exports: PromptExportBundle;
}

export interface PromptGenerationMetadata {
  model: string;
  prompt_id: string;
  prompt_version: string;
  schema_version: string;
  elapsed_ms: number;
  llm_attempts: number;
  format_repaired: boolean;
  candidate_mapping_count: number;
  turn: number;
  input_tokens?: number | null;
  output_tokens?: number | null;
  total_tokens?: number | null;
}

export interface PromptExportBundle {
  markdown: string;
  jira: string;
  issue: string;
}

export interface PromptSessionResponse {
  session_id: string;
  mode: PromptMode;
  persona: PromptPersona;
  turn: number;
  max_turns: number;
  expires_at: string;
  latest_result: PromptResult;
}
