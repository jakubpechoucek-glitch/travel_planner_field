export type ApiResult<T = Record<string, unknown>> = { ok: boolean; status: number; data: T; error: string | null };

/** Calls the API and turns failures into a readable message. Bodies are sent as JSON. */
export async function api<T = Record<string, unknown>>(url: string, method = "GET", body?: unknown): Promise<ApiResult<T>> {
  const r = await fetch(url, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const data = (r.status === 204 ? {} : await r.json().catch(() => ({}))) as T & { detail?: unknown };
  const error = r.ok ? null : typeof data.detail === "string" ? data.detail : "The request failed. Please try again.";
  return { ok: r.ok, status: r.status, data, error };
}
