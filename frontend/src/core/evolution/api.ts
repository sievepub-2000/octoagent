import { getJSON, postJSON, putJSON } from "@/core/api/http";

import type {
  EvolutionConfig,
  EvolutionRecord,
  HealthReport,
  QualityMetrics,
  SkillVersion,
} from "./type";

export async function loadEvolutionConfig(): Promise<EvolutionConfig> {
  const json = await getJSON<{ config: EvolutionConfig }>(
    "/api/skill-evolution/config",
  );
  return json.config;
}

export async function updateEvolutionConfig(
  config: EvolutionConfig,
): Promise<EvolutionConfig> {
  const json = await putJSON<{ config: EvolutionConfig }>(
    "/api/skill-evolution/config",
    config,
  );
  return json.config;
}

export async function loadEvolvedSkills(): Promise<string[]> {
  const json = await getJSON<{ skills: string[] }>(
    "/api/skill-evolution/skills",
  );
  return json.skills;
}

export async function loadSkillVersions(
  skillName: string,
): Promise<SkillVersion[]> {
  const json = await getJSON<{ versions: SkillVersion[] }>(
    `/api/skill-evolution/skills/${skillName}/versions`,
  );
  return json.versions;
}

export async function loadEvolutionRecords(
  limit = 50,
): Promise<EvolutionRecord[]> {
  const json = await getJSON<{ records: EvolutionRecord[] }>(
    `/api/skill-evolution/records?limit=${limit}`,
  );
  return json.records;
}

export async function loadQualityMetrics(): Promise<QualityMetrics[]> {
  const json = await getJSON<{ metrics: QualityMetrics[] }>(
    "/api/skill-evolution/metrics",
  );
  return json.metrics;
}

export async function loadHealthReports(): Promise<HealthReport[]> {
  return getJSON<HealthReport[]>("/api/skill-evolution/health");
}

export async function registerEvolutionSkill(skillName: string): Promise<SkillVersion[]> {
  const json = await postJSON<{ versions: SkillVersion[] }>(`/api/skill-evolution/skills/${skillName}/register`, {});
  return json.versions;
}
