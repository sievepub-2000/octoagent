export type MlInternProfileName = "interactive" | "headless";

export const ML_INTERN_SOURCE_REPO = "https://github.com/huggingface/ml-intern";
export const ML_INTERN_SOURCE_COMMIT = "ff8c636fbb905c4e9a4ba230ed599ab130707c61";

export function resolveMlInternProfile(options: {
  permissionMode?: "approval" | "directory" | "system";
  workflowRunMode?: string | null;
  mode?: string | null;
  yoloMode?: boolean | null;
} = {}): MlInternProfileName {
  const rawMode = `${options.workflowRunMode ?? options.mode ?? ""}`.toLowerCase();
  if (options.permissionMode === "system" || options.yoloMode === true) {
    return "headless";
  }
  if (["headless", "scheduled", "schedule", "timed", "timer", "yolo", "auto"].includes(rawMode)) {
    return "headless";
  }
  return "interactive";
}

export function buildMlInternThreadContext(profile: MlInternProfileName) {
  return {
    ml_intern_profile: profile,
    ml_intern_source_repo: ML_INTERN_SOURCE_REPO,
    ml_intern_source_commit: ML_INTERN_SOURCE_COMMIT,
  };
}

