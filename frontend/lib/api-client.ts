import { getFirebaseAuth } from "@/lib/firebase";
import type { ApiErrorBody } from "@/lib/types";

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

/** Thrown for any non-2xx response, carrying the error envelope's code. */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(message: string, code: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

async function authHeader(): Promise<Record<string, string>> {
  const user = getFirebaseAuth().currentUser;
  if (!user) return {};
  const token = await user.getIdToken();
  return { Authorization: `Bearer ${token}` };
}

/** Typed fetch wrapper that attaches the Firebase token and unwraps the
 *  backend error envelope into an {@link ApiError}. */
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = {
    "Content-Type": "application/json",
    ...(await authHeader()),
    ...(init?.headers ?? {}),
  };
  const response = await fetch(`${BASE_URL}${path}`, { ...init, headers });

  if (!response.ok) {
    let code = "http_error";
    let message = response.statusText || "Request failed";
    try {
      const body = (await response.json()) as Partial<ApiErrorBody>;
      if (body.error) {
        code = body.error.code;
        message = body.error.message;
      }
    } catch {
      // Non-JSON error body — keep the status text.
    }
    throw new ApiError(message, code, response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

/** POST a JSON body and trigger a browser download of the binary response.
 *  Used for exports — the file is built server-side under the caller's RBAC. */
export async function apiDownload(
  path: string,
  body: unknown,
  filename: string,
): Promise<void> {
  const headers = {
    "Content-Type": "application/json",
    ...(await authHeader()),
  };
  const response = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    let code = "http_error";
    let message = response.statusText || "Export failed";
    try {
      const errorBody = (await response.json()) as Partial<ApiErrorBody>;
      if (errorBody.error) {
        code = errorBody.error.code;
        message = errorBody.error.message;
      }
    } catch {
      // Non-JSON error body — keep the status text.
    }
    throw new ApiError(message, code, response.status);
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

/** Build a query string, expanding string arrays into repeated params. */
export function buildQuery(params: Record<string, string | number | boolean | string[] | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === "") continue;
    if (Array.isArray(value)) {
      for (const item of value) search.append(key, item);
    } else {
      search.append(key, String(value));
    }
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}
