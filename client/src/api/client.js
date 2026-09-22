const BASE_URL = '/api';
const TOKEN_KEY = 'aura-screen.token';

/** The session token issued at sign-in, remembered across reloads. */
export const getToken = () => {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
};

export const setToken = (token) => {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* private browsing — the session simply lasts until reload */
  }
};

async function send(path, { method = 'GET', body } = {}) {
  const token = getToken();
  const isForm = body instanceof FormData;

  const response = await fetch(`${BASE_URL}${path}`, {
    method,
    headers: {
      ...(body && !isForm ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: isForm ? body : body ? JSON.stringify(body) : undefined,
  });

  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    const error = new Error(detail.error || `Request failed: ${path}`);
    error.status = response.status;
    throw error;
  }

  return response.status === 204 ? null : response.json();
}

export const request = (path) => send(path);
export const post = (path, body) => send(path, { method: 'POST', body });
export const put = (path, body) => send(path, { method: 'PUT', body });
export const del = (path) => send(path, { method: 'DELETE' });
