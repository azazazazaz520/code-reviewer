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
  session_id: string | null;
  expires_at: string | null;
  metadata: Record<string, number | string>;
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
