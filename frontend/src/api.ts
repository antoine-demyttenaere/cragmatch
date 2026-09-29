export const API_URL = "http://localhost:8000";


// Turn a failed response into a readable message. The backend's errors come
// in three shapes:
//   - our own HTTPExceptions:        {"detail": "some message"}
//   - FastAPI request validation:    {"detail": [{"msg": "...", ...}, ...]}
//   - slowapi's rate limit (429):    {"error": "Rate limit exceeded: 10 per 1 minute"}
export async function errorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail) && body.detail[0]?.msg) return body.detail[0].msg;
    if (typeof body.error === "string") return body.error;
  } catch {
    // The body wasn't JSON (e.g. a plain-text 500): fall through.
  }
  return `Request failed (HTTP ${response.status})`;
}


// fetch + JSON + error handling in one place. Throws an Error with a
// readable message on any non-2xx response.
export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: init?.body ? { "Content-Type": "application/json", ...init.headers } : init?.headers,
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  // 204 No Content (e.g. DELETE) has no body to parse.
  return response.status === 204 ? (undefined as T) : response.json();
}
