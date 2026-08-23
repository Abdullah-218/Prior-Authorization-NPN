// Shared HTTP client for the real Node/Express backend — lets every
// services/*.js module be a thin, consistent wrapper instead of
// re-deriving the token/base-URL/error-handling pattern itself.
export const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5001/api';

const TOKEN_KEY = 'token';

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || '';
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

async function request(path, { method = 'GET', body, isFormData = false, includeMeta = false } = {}) {
  const token = getToken();
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (!isFormData && body !== undefined) headers['Content-Type'] = 'application/json';

  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    // Every list this app renders (queue, dashboards, patient status)
    // needs to reflect the DB the instant it changes — a browser-cached
    // GET (some browsers will cache an identical fetch() URL even without
    // explicit opt-in headers) would show a denied/approved request as
    // still pending after a real, successful decision. no-store forces
    // every call straight to the network.
    cache: 'no-store',
    body: isFormData ? body : body !== undefined ? JSON.stringify(body) : undefined,
  });

  // Backend always responds { success, data, message } even on error
  // (see ProAuth_AI_BackEnd's error middleware) — parse defensively in
  // case something upstream returns a non-JSON body (e.g. a raw 502).
  const payload = await response.json().catch(() => null);
  if (!response.ok || !payload?.success) {
    throw new Error(payload?.message || `Request failed (${response.status})`);
  }
  // includeMeta: some endpoints attach pagination fields (total/page/
  // totalPages) alongside data — callers that need those ask for the full
  // envelope instead of just payload.data.
  return includeMeta ? payload : payload.data;
}

// Binary responses (document file streaming) never go through the
// {success,data,message} JSON envelope above — a real file's Content-Type
// is whatever the document's own mimeType is, not application/json — so
// this is a separate, parallel path rather than a mode of request().
async function requestBlob(path) {
  const token = getToken();
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${API_BASE}${path}`, { method: 'GET', headers, cache: 'no-store' });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.message || `Request failed (${response.status})`);
  }
  return response.blob();
}

export const apiClient = {
  get: (path) => request(path, { method: 'GET' }),
  getWithMeta: (path) => request(path, { method: 'GET', includeMeta: true }),
  getBlob: (path) => requestBlob(path),
  post: (path, body) => request(path, { method: 'POST', body }),
  postForm: (path, formData) => request(path, { method: 'POST', body: formData, isFormData: true }),
  patch: (path, body) => request(path, { method: 'PATCH', body }),
};
