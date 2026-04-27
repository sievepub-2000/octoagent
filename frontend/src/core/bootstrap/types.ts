export interface BootstrapStatus {
  enabled: boolean;
  framework: string;
  repo_id: string;
  filename: string;
  model_path: string;
  installed: boolean;
  onboarding_enabled: boolean;
  use_for_embeddings: boolean;
  vector_store_path: string;
  starter_prompts: string[];
  documents: number;
  namespaces: number;
  n_ctx: number;
  n_batch: number;
  n_threads: number;
  recommended_model: string;
  size_bytes?: number | null;
  corpus_files: string[];
}

export interface BootstrapGuideResponse {
  message: string;
  suggestions: string[];
  evidence: string[];
}

export interface BootstrapInstallResponse {
  installed: boolean;
  model_path: string;
  documents: number;
  namespaces: number;
}
