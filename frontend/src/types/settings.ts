export type SettingsSource = "default" | "env" | "user_file";
export type SecretState = "configured" | "not_configured";

export interface LLMSettings {
  provider: "deepseek-openai-compatible";
  model: string;
  base_url: string;
  temperature: number;
  max_tokens: number;
}

export interface ReviewSettings {
  max_reflection_rounds: number;
  context_files_per_round: number;
  crg_enabled: boolean;
}

export interface PromptSettings {
  timeout_seconds: number;
  min_input_chars: number;
  max_input_chars: number;
  max_output_tokens: number;
  session_ttl_seconds: number;
  session_max_count: number;
  session_max_context_chars: number;
}

export interface StorageSettings {
  repos_dir: string;
}

export interface UserSettings {
  llm: LLMSettings;
  review: ReviewSettings;
  prompt: PromptSettings;
  storage: StorageSettings;
}

export interface SecretStatus {
  llm_api_key: SecretState;
  github_token: SecretState;
  gitee_token: SecretState;
}

export interface EffectiveSettingsSnapshot {
  schema_version: number;
  config_version: number;
  sources: Record<string, SettingsSource>;
  settings: UserSettings;
  secret_status: SecretStatus;
}

export type SettingsSection =
  | "appearance"
  | "model"
  | "git"
  | "review"
  | "prompt"
  | "storage"
  | "about";
