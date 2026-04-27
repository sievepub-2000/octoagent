import { getJSON, postJSON } from "../api/http";

import type {
  CreateResearchExperimentRequest,
  ResearchExperiment,
  ResearchExperimentListResponse,
  ResearchExperimentRunResponse,
  ResearchProgramListResponse,
  ResearchRuntimeCapability,
  ResearchTrial,
  RunResearchExperimentRequest,
} from "./types";

export function loadResearchRuntimeCapabilities() {
  return getJSON<ResearchRuntimeCapability>("/api/research-runtime/capabilities");
}

export function loadResearchPrograms() {
  return getJSON<ResearchProgramListResponse>("/api/research-runtime/programs");
}

export function loadResearchExperiments() {
  return getJSON<ResearchExperimentListResponse>("/api/research-runtime/experiments");
}

export function createResearchExperiment(payload: CreateResearchExperimentRequest) {
  return postJSON<ResearchExperiment>("/api/research-runtime/experiments", payload);
}

export function loadResearchExperiment(experimentId: string) {
  return getJSON<ResearchExperiment>(`/api/research-runtime/experiments/${experimentId}`);
}

export function loadResearchTrials(experimentId: string) {
  return getJSON<ResearchTrial[]>(`/api/research-runtime/experiments/${experimentId}/trials`);
}

export function runResearchExperiment(
  experimentId: string,
  payload: RunResearchExperimentRequest,
) {
  return postJSON<ResearchExperimentRunResponse>(
    `/api/research-runtime/experiments/${experimentId}/run`,
    payload,
  );
}
