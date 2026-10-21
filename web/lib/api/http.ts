import { authHeaders, handleUnauthorized } from "@/lib/auth";
import { parseApiError } from "@/lib/errors";

export type HttpOptions = RequestInit & { skipAuthRedirect?: boolean; skipAuth?: boolean };

/** Typed JSON fetch with cookie auth and consistent error handling. */
export async function http<T>(path: string, init?: HttpOptions): Promise<T> {
  const { skipAuthRedirect, skipAuth, ...requestInit } = init ?? {};

  const res = await fetch(path, {
    ...requestInit,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(skipAuth ? {} : authHeaders()),
      ...(requestInit.headers || {}),
    },
  });
  if (res.status === 401 && typeof window !== "undefined") {
    const text = await res.text();
    if (!skipAuthRedirect) {
      handleUnauthorized();
      throw new Error("401 unauthorized");
    }
    throw new Error(parseApiError(new Error(`${res.status} ${text}`)));
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(parseApiError(new Error(`${res.status} ${text}`)));
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}
