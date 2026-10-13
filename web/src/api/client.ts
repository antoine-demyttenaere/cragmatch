export const API_URL = "http://localhost:8000";


// An HTTP failure with its status, so screens can treat some statuses (422,
// 429, 503 from the AI searches) as a notice instead of an error.
export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}


// Turn a failed response into a readable message. The backend's errors come
// in three shapes:
//   - our own HTTPExceptions:        {"detail": "some message"}
//   - FastAPI request validation:    {"detail": [{"msg": "...", ...}, ...]}
//   - slowapi's rate limit (429):    {"error": "Rate limit exceeded: 10 per 1 minute"}
export async function errorMessage(response: Response): Promise<string> {
  if (response.status === 429) return "Too many searches. Try again in a minute.";
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


// fetch + JSON + error handling in one place. Throws an ApiError on any
// non-2xx response and a plain Error when the server can't be reached.
export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: init?.body ? { "Content-Type": "application/json", ...init.headers } : init?.headers,
    });
  } catch {
    // fetch only rejects when no response came back at all (server down, offline).
    throw new Error("Can't reach the CragMatch server. Is the backend running?");
  }
  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response));
  }
  // 204 No Content (e.g. DELETE) has no body to parse.
  return response.status === 204 ? (undefined as T) : response.json();
}
