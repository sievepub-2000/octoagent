import { deleteJSON, getJSON, postJSON, putJSON } from "../api/http";

import type {
  ChannelConfigUpdateRequest,
  ChannelConfigUpdateResponse,
  ChannelEnabledUpdateResponse,
  ChannelIdentityStatus,
  ChannelLogoutResponse,
  ChannelRestartResponse,
  ChannelStatusResponse,
} from "./types";

export async function loadChannelsStatus() {
  return getJSON<ChannelStatusResponse>("/api/channels/");
}

export async function restartChannel(name: string) {
  return postJSON<ChannelRestartResponse>(`/api/channels/${encodeURIComponent(name)}/restart`);
}

export async function updateChannelConfig(
  name: string,
  payload: ChannelConfigUpdateRequest,
) {
  return putJSON<ChannelConfigUpdateResponse>(
    `/api/channels/${encodeURIComponent(name)}/config`,
    payload,
  );
}

export async function setChannelEnabled(name: string, enabled: boolean) {
  return putJSON<ChannelEnabledUpdateResponse>(
    `/api/channels/${encodeURIComponent(name)}/enabled`,
    { enabled },
  );
}

export async function deleteChannelConfig(name: string) {
  return deleteJSON<ChannelConfigUpdateResponse>(
    `/api/channels/${encodeURIComponent(name)}/config`,
  );
}

export async function logoutChannel(name: string) {
  return postJSON<ChannelLogoutResponse>(`/api/channels/${encodeURIComponent(name)}/logout`);
}

export async function loadChannelIdentity(name: string) {
  return getJSON<ChannelIdentityStatus>(`/api/channels/${encodeURIComponent(name)}/identity`);
}
