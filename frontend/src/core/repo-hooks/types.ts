export type RepoHookTrigger = {
  trigger: string;
  command_count: number;
};

export type RepoHook = {
  name: string;
  description: string;
  enabled: boolean;
  triggers: RepoHookTrigger[];
  files: string[];
};

export type RepoHooksResponse = {
  hooks: RepoHook[];
};