const ADMIN_TOKEN_KEY = "kitescope_admin_token";
const USER_TOKEN_KEY = "kitescope_user_token";

export function getAdminToken(): string | null {
  return localStorage.getItem(ADMIN_TOKEN_KEY);
}

export function setAdminToken(token: string): void {
  localStorage.setItem(ADMIN_TOKEN_KEY, token);
}

export function clearAdminToken(): void {
  localStorage.removeItem(ADMIN_TOKEN_KEY);
}

export function getUserToken(): string | null {
  return localStorage.getItem(USER_TOKEN_KEY);
}

export function setUserToken(token: string): void {
  localStorage.setItem(USER_TOKEN_KEY, token);
}

export function clearUserToken(): void {
  localStorage.removeItem(USER_TOKEN_KEY);
}

/** Dispatched when backend returns 401 so admin layout can show login again. */
export const ADMIN_SESSION_EXPIRED_EVENT = "kitescope-admin-session-expired";

/** Dispatched when backend returns 401 so dashboard can show logged-out state. */
export const USER_SESSION_EXPIRED_EVENT = "kitescope-user-session-expired";

export function authFetch(url: string, init?: RequestInit): Promise<Response> {
  const token = getAdminToken();
  const headers = new Headers(init?.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(url, { ...init, headers }).then((res) => {
    if (res.status === 401) {
      clearAdminToken();
      window.dispatchEvent(new CustomEvent(ADMIN_SESSION_EXPIRED_EVENT));
    }
    return res;
  });
}

export function userFetch(url: string, init?: RequestInit): Promise<Response> {
  const token = getUserToken();
  const headers = new Headers(init?.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(url, { ...init, headers }).then((res) => {
    if (res.status === 401) {
      clearUserToken();
      window.dispatchEvent(new CustomEvent(USER_SESSION_EXPIRED_EVENT));
    }
    return res;
  });
}
