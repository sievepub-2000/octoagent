import type { AgentThreadContext } from "../threads";

import {
  DEFAULT_APPEARANCE_PRESET,
  type AppearancePresetId,
} from "./appearance-presets";

export const DEFAULT_LOCAL_SETTINGS: LocalSettings = {
  appearance: {
    preset: DEFAULT_APPEARANCE_PRESET,
  },
  notification: {
    enabled: true,
  },
  bootstrap: {
    onboarding_enabled: true,
  },
  context: {
    model_name: undefined,
    agent_name: undefined,
    mode: "pro",
    reasoning_effort: "high",
    permission_mode: "directory",
    conversation_language: undefined,
    ml_intern_profile: undefined,
  },
  layout: {
    sidebar_collapsed: false,
  },
  setup: {
    completed: false,
    workspace_path: "",
    default_model: "",
    sandbox_mode: "local",
  },
};

const LOCAL_SETTINGS_KEY = "octoagent.local-settings";
export const LOCAL_SETTINGS_CHANGE_EVENT = "octoagent:local-settings-change";

export interface LocalSettings {
  appearance: {
    preset: AppearancePresetId;
  };
  notification: {
    enabled: boolean;
  };
  bootstrap: {
    onboarding_enabled: boolean;
  };
  context: Omit<
    AgentThreadContext,
    "thread_id" | "is_plan_mode" | "thinking_enabled" | "subagent_enabled"
  > & {
    mode: "flash" | "thinking" | "pro" | "ultra" | undefined;
    reasoning_effort?: "minimal" | "low" | "medium" | "high";
    permission_mode?: "approval" | "directory" | "system";
  };
  layout: {
    sidebar_collapsed: boolean;
  };
  setup: {
    completed: boolean;
    workspace_path: string;
    default_model: string;
    sandbox_mode: "local" | "docker";
  };
}

export function getLocalSettings(): LocalSettings {
  if (typeof window === "undefined") {
    return DEFAULT_LOCAL_SETTINGS;
  }
  const json = localStorage.getItem(LOCAL_SETTINGS_KEY);
  try {
    if (json) {
      const settings = JSON.parse(json);
      const mergedSettings = {
        ...DEFAULT_LOCAL_SETTINGS,
        appearance: {
          ...DEFAULT_LOCAL_SETTINGS.appearance,
          ...settings.appearance,
        },
        context: {
          ...DEFAULT_LOCAL_SETTINGS.context,
          ...settings.context,
        },
        layout: {
          ...DEFAULT_LOCAL_SETTINGS.layout,
          ...settings.layout,
        },
        notification: {
          ...DEFAULT_LOCAL_SETTINGS.notification,
          ...settings.notification,
        },
        bootstrap: {
          ...DEFAULT_LOCAL_SETTINGS.bootstrap,
          ...settings.bootstrap,
        },
        setup: {
          ...DEFAULT_LOCAL_SETTINGS.setup,
          ...settings.setup,
        },
      };
      const legacyLowAutonomyDefaults =
        settings.context?.mode === "flash" &&
        settings.context?.reasoning_effort === "minimal" &&
        settings.context?.permission_mode === "approval";
      if (legacyLowAutonomyDefaults) {
        mergedSettings.context = {
          ...mergedSettings.context,
          mode: "pro",
          reasoning_effort: "high",
          permission_mode: "directory",
        };
        localStorage.setItem(LOCAL_SETTINGS_KEY, JSON.stringify(mergedSettings));
      }
      return mergedSettings;
    }
  } catch {}
  return DEFAULT_LOCAL_SETTINGS;
}

export function saveLocalSettings(settings: LocalSettings) {
  try {
    localStorage.setItem(LOCAL_SETTINGS_KEY, JSON.stringify(settings));
    // Defer the event so listeners' setState calls don't fire inside another
    // component's render cycle (avoids "Cannot update a component while
    // rendering a different component" React warning).
    queueMicrotask(() => {
      window.dispatchEvent(new Event(LOCAL_SETTINGS_CHANGE_EVENT));
    });
  } catch {
    // QuotaExceededError or other storage errors — settings not persisted
  }
}
