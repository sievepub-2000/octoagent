import { env } from "@/env";

function getConfiguredPort(value: string | undefined, fallback: string) {
  return value?.trim() ? value.trim() : fallback;
}

function isLocalHostname(hostname: string) {
  return (
    hostname === "localhost" ||
    hostname === "127.0.0.1" ||
    hostname === "0.0.0.0" ||
    hostname.endsWith(".local") ||
    hostname.startsWith("10.") ||
    hostname.startsWith("192.168.") ||
    /^172\.(1[6-9]|2\d|3[0-1])\./.test(hostname)
  );
}

function shouldUseIngressProxy() {
  if (typeof window === "undefined") {
    return false;
  }

  const { hostname, port } = window.location;
  if (!isLocalHostname(hostname)) {
    return true;
  }

  return port !== "19886";
}

export function getBackendBaseURL() {
  const gatewayPort = getConfiguredPort(env.NEXT_PUBLIC_LOCAL_GATEWAY_PORT, "19882");
  const ingressPort = getConfiguredPort(env.NEXT_PUBLIC_LOCAL_INGRESS_PORT, "19880");

  if (env.NEXT_PUBLIC_BACKEND_BASE_URL) {
    return env.NEXT_PUBLIC_BACKEND_BASE_URL;
  } else if (shouldUseIngressProxy()) {
    return typeof window !== "undefined"
      ? window.location.origin
      : `http://127.0.0.1:${ingressPort}`;
  } else if (typeof window !== "undefined" && isLocalHostname(window.location.hostname)) {
    return `${window.location.protocol}//${window.location.hostname}:${gatewayPort}`;
  } else {
    return "";
  }
}

export function getLangGraphBaseURL(isMock?: boolean) {
  const frontendPort = getConfiguredPort(env.NEXT_PUBLIC_LOCAL_FRONTEND_PORT, "19886");
  const langgraphPort = getConfiguredPort(env.NEXT_PUBLIC_LOCAL_LANGGRAPH_PORT, "19884");
  const ingressPort = getConfiguredPort(env.NEXT_PUBLIC_LOCAL_INGRESS_PORT, "19880");

  if (env.NEXT_PUBLIC_LANGGRAPH_BASE_URL) {
    return env.NEXT_PUBLIC_LANGGRAPH_BASE_URL;
  } else if (isMock) {
    if (typeof window !== "undefined") {
      return `${window.location.origin}/mock/api`;
    }
    return `http://localhost:${frontendPort}/mock/api`;
  } else {
    if (shouldUseIngressProxy()) {
      return typeof window !== "undefined"
        ? `${window.location.origin}/api/langgraph`
        : `http://127.0.0.1:${ingressPort}/api/langgraph`;
    }
    if (typeof window !== "undefined" && isLocalHostname(window.location.hostname)) {
      return `${window.location.protocol}//${window.location.hostname}:${langgraphPort}`;
    }
    // LangGraph SDK requires a full URL, construct it from current origin
    if (typeof window !== "undefined") {
      return `${window.location.origin}/api/langgraph`;
    }
    // Fallback for SSR / standalone local runtime
    return `http://localhost:${langgraphPort}`;
  }
}
