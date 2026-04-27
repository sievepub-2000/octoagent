import type { Model } from "./types";

export const MODEL_NONE = "__none__";
export const PROVIDER_ALL = "__all__";

export type ModelSelectionOption = Pick<Model, "name" | "display_name" | "provider_name">;

export function findModelByValue(
  models: Model[],
  value: string | null | undefined,
): Model | null {
  if (!value || value === MODEL_NONE) {
    return null;
  }
  return models.find((model) => model.name === value || model.id === value) ?? null;
}

export function getModelProviderValue(
  models: Model[],
  value: string | null | undefined,
): string {
  const matched = findModelByValue(models, value);
  const provider = matched?.provider_name?.trim();
  return provider && provider.length > 0 ? provider : PROVIDER_ALL;
}

export function listProviderValues(models: Model[]): string[] {
  return Array.from(
    new Set(
      models
        .map((model) => model.provider_name?.trim())
        .filter((provider): provider is string => Boolean(provider && provider.length > 0)),
    ),
  ).sort((left, right) => left.localeCompare(right));
}

export function listModelOptionsForProvider(
  models: Model[],
  provider: string,
  currentValue?: string | null,
): ModelSelectionOption[] {
  const filtered = provider === PROVIDER_ALL
    ? models
    : models.filter((model) => (model.provider_name?.trim() ?? "") === provider);

  const options = filtered.map((model) => ({
    name: model.name,
    display_name: model.display_name,
    provider_name: model.provider_name,
  }));

  if (
    currentValue
    && currentValue !== MODEL_NONE
    && !options.some((option) => option.name === currentValue)
  ) {
    const current = findModelByValue(models, currentValue);
    options.unshift({
      name: current?.name ?? currentValue,
      display_name: current?.display_name ?? currentValue,
      provider_name: current?.provider_name ?? null,
    });
  }

  return options;
}

export function resolveModelDisplayName(
  models: Model[],
  value: string | null | undefined,
): string | null {
  if (!value || value === MODEL_NONE) {
    return null;
  }
  const matched = findModelByValue(models, value);
  return matched?.display_name ?? matched?.name ?? value;
}