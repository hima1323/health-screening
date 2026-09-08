const BASE_URL = '/api';

export async function request(path) {
  const response = await fetch(`${BASE_URL}${path}`);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.error || `Request failed: ${path}`);
  }
  return response.json();
}
