/**
 * Auth: JWT in HttpOnly cookie (set by backend on login). Frontend uses credentials: "include"
 * and does not read the token (XSS cannot steal it).
 */

const API = "/api";

/** Dispatched when backend returns 401 so admin layout can show login again. */
export const ADMIN_SESSION_EXPIRED_EVENT = "kitescope-admin-session-expired";

/** Dispatched when backend returns 401 so dashboard can show logged-out state. */
export const USER_SESSION_EXPIRED_EVENT = "kitescope-user-session-expired";

export function getAdminToken(): string | null {
  return null;
}

export function setAdminToken(_token: string): void {}

export function clearAdminToken(): void {}

export function getUserToken(): string | null {
  return null;
}

export function setUserToken(_token: string): void {}

export function clearUserToken(): void {}

/** Call backend to clear admin cookie, then dispatch session expired. */
export async function logoutAdmin(): Promise<void> {
  await fetch(`${API}/auth/admin/logout`, { method: "POST", credentials: "include" });
  window.dispatchEvent(new CustomEvent(ADMIN_SESSION_EXPIRED_EVENT));
}

/** Call backend to clear user cookie, then dispatch session expired. */
export async function logoutUser(): Promise<void> {
  await fetch(`${API}/auth/logout`, { method: "POST", credentials: "include" });
  window.dispatchEvent(new CustomEvent(USER_SESSION_EXPIRED_EVENT));
}

export function authFetch(url: string, init?: RequestInit): Promise<Response> {
  return fetch(url, { ...init, credentials: "include" }).then((res) => {
    if (res.status === 401) {
      window.dispatchEvent(new CustomEvent(ADMIN_SESSION_EXPIRED_EVENT));
    }
    return res;
  });
}

export function userFetch(url: string, init?: RequestInit): Promise<Response> {
  return fetch(url, { ...init, credentials: "include" }).then((res) => {
    if (res.status === 401) {
      window.dispatchEvent(new CustomEvent(USER_SESSION_EXPIRED_EVENT));
    }
    return res;
  });
}
