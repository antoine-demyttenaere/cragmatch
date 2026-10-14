export const API_URL = "http://localhost:8000";


// An HTTP failure with its status, so screens can treat some statuses (422,
// 429, 503 from the AI searches) as a notice instead of an error.
export class ApiError extends Error {
  status: number;
  // The request field a validation error is about ("max_distance_km"), or
  // null when it is about the whole request.
  field: string | null;

  constructor(status: number, message: string, field: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.field = field;
  }
}


interface ErrorDetails {
  message: string;
  field: string | null;
}

// FastAPI's `loc` is ["body", "max_distance_km"] or ["query", "mode"]; a
// model-level error has just ["body"]. Only a real field name is useful.
function fieldFromLoc(loc: unknown): string | null {
  if (!Array.isArray(loc) || loc.length === 0) return null;
  const last = loc[loc.length - 1];
  if (typeof last !== "string" || last === "body" || last === "query") return null;
  return last;
}

// Turn a failed response into a readable message. The backend's errors come
// in three shapes:
//   - our own HTTPExceptions:        {"detail": "some message"}
//   - FastAPI request validation:    {"detail": [{"msg": "...", "loc": [...]}, ...]}
//   - slowapi's rate limit (429):    {"error": "Rate limit exceeded: 10 per 1 minute"}
export async function errorDetails(response: Response): Promise<ErrorDetails> {
  if (response.status === 429) return { message: "Too many searches. Try again in a minute.", field: null };
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return { message: body.detail, field: null };
    if (Array.isArray(body.detail) && body.detail[0]?.msg) {
      // Pydantic puts "Value error, " in front of our own validators' messages.
      const message = String(body.detail[0].msg).replace(/^Value error, /, "");
      return { message, field: fieldFromLoc(body.detail[0].loc) };
    }
    if (typeof body.error === "string") return { message: body.error, field: null };
  } catch {
    // The body wasn't JSON (e.g. a plain-text 500): fall through.
  }
  return { message: `Request failed (HTTP ${response.status})`, field: null };
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
    const { message, field } = await errorDetails(response);
    throw new ApiError(response.status, message, field);
  }
  // 204 No Content (e.g. DELETE) has no body to parse.
  return response.status === 204 ? (undefined as T) : response.json();
}
