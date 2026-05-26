import { deleteJSON, getJSON, postJSON } from "../api/http";

import type {
  PluginCapabilityListResponse,
  PluginInstallRequest,
  PluginManifestListResponse,
  PluginRecommendationRequest,
  PluginRecommendationResponse,
  PluginRegistryEntry,
  PluginRegistryResponse,
} from "./types";

export function loadPluginCapabilities() {
  return getJSON<PluginCapabilityListResponse>("/api/plugins/capabilities");
}

export function loadPluginManifests() {
  return getJSON<PluginManifestListResponse>("/api/plugins/manifests");
}

export function loadPluginRegistry() {
  return getJSON<PluginRegistryResponse>("/api/plugins/registry");
}

export function loadPluginRecommendations(payload: PluginRecommendationRequest) {
  return postJSON<PluginRecommendationResponse>("/api/plugins/recommendations", payload);
}

export function installPlugin(payload: PluginInstallRequest) {
  return postJSON<PluginRegistryEntry>("/api/plugins/install", payload);
}

export function enablePlugin(pluginId: string) {
  return postJSON<PluginRegistryEntry>(`/api/plugins/${pluginId}/enable`);
}

export function disablePlugin(pluginId: string) {
  return postJSON<PluginRegistryEntry>(`/api/plugins/${pluginId}/disable`);
}

export function uninstallPlugin(pluginId: string) {
  return deleteJSON(`/api/plugins/${pluginId}`);
}
