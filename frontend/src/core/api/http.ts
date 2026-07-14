import { getBackendBaseURL } from "../config";

type Primitive = string | number | boolean;
type QueryValue = Primitive | null | undefined;
type JSONBody = object;

type RequestOptions = Omit<RequestInit, "body"> & {
  body?: BodyInit | JSONBody | null;
  query?: Record<string, QueryValue>;
};

async function parseError(response: Response): Promise<string> {
  const fallback = `HTTP ${response.status}: ${response.statusText || "Request failed"}`;
  const contentType = response.headers.get("content-type") ?? "";

  try {
    if (contentType.includes("application/json")) {
      const data = (await response.json()) as { detail?: string; message?: string };
      return data.detail ?? data.message ?? fallback;
    }

    const text = (await response.text()).trim();
    return text || fallback;
  } catch {
    return fallback;
  }
}

function buildURL(path: string, query?: Record<string, QueryValue>) {
  const backendBaseURL = getBackendBaseURL();
  const baseURL =
    backendBaseURL ||
    (typeof window !== "undefined"
      ? window.location.origin
      : "http://127.0.0.1:19880");
  const url = new URL(path, baseURL);
  if (!query) {
    return url.toString();
  }

  for (const [key, value] of Object.entries(query)) {
    if (value == null) {
      continue;
    }
    url.searchParams.set(key, String(value));
  }
  return url.toString();
}

export async function apiRequest<T>(
  path: string,
  { body, headers, query, ...init }: RequestOptions = {},
): Promise<T> {
  const requestHeaders = new Headers(headers);
  if (typeof window !== "undefined") {
    const sessionToken = localStorage.getItem("octoagent_session_token");
    const tenantId = localStorage.getItem("octoagent_tenant_id");
    const operatorToken = sessionStorage.getItem("octoagent_operator_token");
    if (sessionToken && !requestHeaders.has("X-OctoAgent-Session-Token")) {
      requestHeaders.set("X-OctoAgent-Session-Token", sessionToken);
    }
    if (tenantId && !requestHeaders.has("X-Tenant-ID")) {
      requestHeaders.set("X-Tenant-ID", tenantId);
    }
    if (operatorToken && !requestHeaders.has("X-OctoAgent-Operator-Token")) {
      requestHeaders.set("X-OctoAgent-Operator-Token", operatorToken);
      requestHeaders.set("X-OctoAgent-Operator-Role", "operator");
    }
  }
  let requestBody: BodyInit | undefined;

  if (body == null) {
    requestBody = undefined;
  } else if (
    body instanceof FormData ||
    body instanceof URLSearchParams ||
    body instanceof Blob ||
    typeof body === "string" ||
    body instanceof ArrayBuffer
  ) {
    requestBody = body;
  } else {
    if (!requestHeaders.has("Content-Type")) {
      requestHeaders.set("Content-Type", "application/json");
    }
    requestBody = JSON.stringify(body);
  }

  const response = await fetch(buildURL(path, query), {
    ...init,
    headers: requestHeaders,
    body: requestBody,
  });

  if (!response.ok) {
    throw new Error(await parseError(response));
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export function getJSON<T>(path: string, query?: Record<string, QueryValue>) {
  return apiRequest<T>(path, { method: "GET", query });
}

export function postJSON<T>(
  path: string,
  body?: RequestOptions["body"],
  options?: Omit<RequestOptions, "body" | "method">,
) {
  return apiRequest<T>(path, { ...options, method: "POST", body });
}

export function putJSON<T>(
  path: string,
  body?: RequestOptions["body"],
  options?: Omit<RequestOptions, "body" | "method">,
) {
  return apiRequest<T>(path, { ...options, method: "PUT", body });
}

export function deleteJSON<T>(
  path: string,
  options?: Omit<RequestOptions, "method">,
) {
  return apiRequest<T>(path, { ...options, method: "DELETE" });
}
