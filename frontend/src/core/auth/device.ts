export async function getDeviceFingerprint() {
  if (typeof window === "undefined") {
    return "server-side-device-placeholder";
  }
  const parts = [
    navigator.userAgent,
    navigator.language,
    navigator.platform,
    Intl.DateTimeFormat().resolvedOptions().timeZone,
    `${screen.width}x${screen.height}x${screen.colorDepth}`,
  ];
  const payload = parts.join("|");
  const bytes = new TextEncoder().encode(payload);
  const subtle = window.crypto?.subtle;
  if (subtle) {
    const digest = await subtle.digest("SHA-256", bytes);
    return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
  }

  // LAN HTTP access is not a secure context in some browsers, so WebCrypto
  // can be unavailable. Keep a deterministic local fingerprint fallback.
  let hashA = 0x811c9dc5;
  let hashB = 0x01000193;
  for (let index = 0; index < payload.length; index += 1) {
    const code = payload.charCodeAt(index);
    hashA ^= code;
    hashA = Math.imul(hashA, 0x01000193);
    hashB ^= code + index;
    hashB = Math.imul(hashB, 0x811c9dc5);
  }
  const hexA = (hashA >>> 0).toString(16).padStart(8, "0");
  const hexB = (hashB >>> 0).toString(16).padStart(8, "0");
  return `${hexA}${hexB}`;
}

export const AUTH_STORAGE_KEYS = {
  session: "octoagent_session_token",
  tenant: "octoagent_tenant_id",
  username: "octoagent_username",
  userId: "octoagent_user_id",
} as const;

export function saveAuthSession(session: {
  session_token: string;
  tenant_id: string;
  username: string;
  user_id: string;
}) {
  localStorage.setItem(AUTH_STORAGE_KEYS.session, session.session_token);
  localStorage.setItem(AUTH_STORAGE_KEYS.tenant, session.tenant_id);
  localStorage.setItem(AUTH_STORAGE_KEYS.username, session.username);
  localStorage.setItem(AUTH_STORAGE_KEYS.userId, session.user_id);
}
