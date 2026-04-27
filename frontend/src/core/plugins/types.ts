export type PluginCommand = {
  command_id: string;
  title: string;
  stage: "ideate" | "brainstorm" | "plan" | "work" | "review" | "compound" | "runtime";
  summary: string;
};

export type PluginManifest = {
  plugin_id: string;
  display_name: string;
  version: string;
  provider: string;
  description: string;
  commands: PluginCommand[];
  installation_targets: string[];
  review_flow: string[];
};

export type PluginRegistryEntry = {
  plugin_id: string;
  installed: boolean;
  enabled: boolean;
  installed_version?: string | null;
  source: "builtin" | "local" | "remote";
  installed_at?: string | null;
};

export type PluginCapability = {
  plugin_id: string;
  display_name: string;
  category: "engineering" | "review" | "runtime" | "integration";
  execution_mode: "advisory" | "tooling" | "workflow";
  manifest?: PluginManifest | null;
  permissions: string[];
  runtime_requirements: string[];
  enabled: boolean;
};

export type PluginCapabilityListResponse = {
  plugins: PluginCapability[];
};

export type PluginManifestListResponse = {
  manifests: PluginManifest[];
};

export type PluginRegistryResponse = {
  entries: PluginRegistryEntry[];
};

export type PluginInstallRequest = {
  plugin_id: string;
  source?: "builtin" | "local" | "remote";
  enable_after_install?: boolean;
};

export type PluginRecommendationRequest = {
  mode?: "single" | "branch" | "group";
  card_kinds?: string[];
};

export type PluginRecommendationResponse = {
  plugin_ids: string[];
};
