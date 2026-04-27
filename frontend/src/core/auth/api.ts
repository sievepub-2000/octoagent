import { postJSON } from "../api/http";

export interface AuthChallengeResponse {
  challenge_id: string;
  expires_at: number;
  delivery: string;
  dev_code?: string | null;
}

export interface AuthSessionResponse {
  session_token: string;
  user_id: string;
  username: string;
  email: string;
  tenant_id: string;
  expires_at: number;
}

export function startRegistration(input: {
  username: string;
  password: string;
  email: string;
  display_name?: string;
}) {
  return postJSON<AuthChallengeResponse>("/api/auth/register/start", input);
}

export function verifyRegistration(input: {
  challenge_id: string;
  code: string;
  device_fingerprint: string;
}) {
  return postJSON<AuthSessionResponse>("/api/auth/register/verify", input);
}

export function login(input: {
  username: string;
  password: string;
  device_fingerprint: string;
}) {
  return postJSON<AuthSessionResponse>("/api/auth/login", input);
}

export function deviceLogin(input: {
  username: string;
  device_fingerprint: string;
}) {
  return postJSON<AuthSessionResponse>("/api/auth/device-login", input);
}

export function startDeviceVerification(input: { username: string }) {
  return postJSON<AuthChallengeResponse>("/api/auth/device/verify/start", input);
}

export function verifyDevice(input: {
  challenge_id: string;
  code: string;
  device_fingerprint: string;
}) {
  return postJSON<AuthSessionResponse>("/api/auth/device/verify", input);
}
