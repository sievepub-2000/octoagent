import { postJSON } from "../api/http";

import type { BrainPlanRequest, BrainResponse } from "./types";

export async function buildBrainPlan(
  payload: BrainPlanRequest,
): Promise<BrainResponse> {
  return postJSON<BrainResponse>("/api/brain/plan", payload);
}
