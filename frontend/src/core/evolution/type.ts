export interface EvolutionConfig {
  enabled: boolean;
  auto_fix: boolean;
  auto_derive: boolean;
  auto_capture: boolean;
  quality_monitoring: boolean;
  evolve_interval: number;
  cloud_enabled: boolean;
  cloud_api_key: string;
  cloud_api_base: string;
}

export interface SkillVersion {
  skill_name: string;
  version: number;
  parent_name: string | null;
  parent_version: number | null;
  mode: "fix" | "derived" | "captured" | null;
  diff_summary: string;
  created_at: string;
}

export interface EvolutionRecord {
  id: string;
  skill_name: string;
  from_version: number;
  to_version: number;
  mode: "fix" | "derived" | "captured";
  reason: string;
  diff_summary: string;
  created_at: string;
}

export interface QualityMetrics {
  skill_name: string;
  applied_count: number;
  success_count: number;
  failure_count: number;
  fallback_count: number;
  avg_latency_ms: number;
  last_used: string | null;
}

export interface HealthReport {
  skill_name: string;
  healthy: boolean;
  success_rate: number;
  applied_rate: number;
  total_executions: number;
  recommendation: string;
}
