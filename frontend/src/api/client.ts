import axios from "axios";

// Base URL for the API. In development Vite proxies ``/api`` to the backend;
// in production set ``VITE_API_URL`` (e.g. https://host/api).
export const API_BASE = import.meta.env.VITE_API_URL ?? "/api";

// Origin used to resolve relative ``/storage/...`` artefact URLs returned by
// the backend into absolute, fetchable URLs.
export const STORAGE_ORIGIN =
  import.meta.env.VITE_STORAGE_ORIGIN ??
  (API_BASE.startsWith("http") ? new URL(API_BASE).origin : "");

export const apiClient = axios.create({
  baseURL: API_BASE,
  headers: { "Content-Type": "application/json" },
});

// --- Bearer-token auth ------------------------------------------------------
// A no-op when the deployment has AUTH_ENABLED=false (the default): no token
// is ever stored, so every request is simply sent without an Authorization
// header, exactly as before this was added.
const TOKEN_STORAGE_KEY = "video-analytics.auth-token";

export function getAuthToken(): string | null {
  return localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function setAuthToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_STORAGE_KEY, token);
  else localStorage.removeItem(TOKEN_STORAGE_KEY);
}

apiClient.interceptors.request.use((config) => {
  const token = getAuthToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

/** Fired when a request comes back 401 so the app can redirect to /login. */
export const AUTH_LOGOUT_EVENT = "video-analytics.auth-logout";

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && getAuthToken()) {
      setAuthToken(null);
      window.dispatchEvent(new Event(AUTH_LOGOUT_EVENT));
    }
    return Promise.reject(error);
  },
);

/** Resolve a relative storage URL (``/storage/...``) to an absolute URL. */
export function resolveStorageUrl(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  if (url.startsWith("http")) return url;
  return `${STORAGE_ORIGIN}${url}`;
}
