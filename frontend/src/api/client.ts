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

/** Resolve a relative storage URL (``/storage/...``) to an absolute URL. */
export function resolveStorageUrl(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  if (url.startsWith("http")) return url;
  return `${STORAGE_ORIGIN}${url}`;
}
