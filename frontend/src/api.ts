const API_BASE = import.meta.env.VITE_API_BASE ?? "";
const BOOTSTRAP_KEY = import.meta.env.VITE_AUTH_BOOTSTRAP_KEY ?? "dev-bootstrap-key";
const SIGNING_KEY = import.meta.env.VITE_API_SIGNING_KEY ?? "change-this-signing-key";
const CLIENT_ID = import.meta.env.VITE_CLIENT_ID ?? "web-client";

type Envelope<T> = { code: number; message: string; data: T };
type AuthTokenResponse = { access_token: string; token_type: string };

let accessToken: string | null = null;

async function parse<T>(res: Response): Promise<T> {
  const j = (await res.json()) as Envelope<T>;
  if (!res.ok || j.code !== 0) {
    throw new Error(j.message || `HTTP ${res.status}`);
  }
  return j.data;
}

function withLang(path: string, lang: string): string {
  const sep = path.includes("?") ? "&" : "?";
  return `${API_BASE}${path}${sep}lang=${lang}`;
}

function toAbsUrl(pathWithQuery: string): URL {
  return new URL(pathWithQuery, window.location.origin);
}

async function sha256Hex(input: string): Promise<string> {
  const data = new TextEncoder().encode(input);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

async function hmacHex(key: string, message: string): Promise<string> {
  const keyData = new TextEncoder().encode(key);
  const cryptoKey = await crypto.subtle.importKey("raw", keyData, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", cryptoKey, new TextEncoder().encode(message));
  return Array.from(new Uint8Array(sig))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

async function ensureAccessToken(): Promise<string> {
  if (accessToken) return accessToken;
  const url = `${API_BASE}/api/v1/auth/token`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "x-bootstrap-key": BOOTSTRAP_KEY,
      "x-client-id": CLIENT_ID,
      "Content-Type": "application/json",
    },
    body: "{}",
  });
  const data = await parse<AuthTokenResponse>(res);
  accessToken = data.access_token;
  return accessToken;
}

async function signedFetch(path: string, lang: string, init?: RequestInit): Promise<Response> {
  const token = await ensureAccessToken();
  const full = withLang(path, lang);
  const url = toAbsUrl(full);
  const method = (init?.method ?? "GET").toUpperCase();
  const bodyText = typeof init?.body === "string" ? init.body : "";
  const ts = Math.floor(Date.now() / 1000).toString();
  const bodyHash = await sha256Hex(bodyText);
  const canonical = [method, url.pathname, url.search.slice(1), ts, bodyHash].join("\n");
  const signature = await hmacHex(SIGNING_KEY, canonical);

  const headers = new Headers(init?.headers ?? {});
  headers.set("Authorization", `Bearer ${token}`);
  headers.set("x-ts", ts);
  headers.set("x-signature", signature);
  if (bodyText && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return fetch(url.toString(), { ...init, method, headers });
}

export async function apiGet<T>(path: string, lang: string): Promise<T> {
  const res = await signedFetch(path, lang, { method: "GET" });
  return parse<T>(res);
}

export async function apiPost<T>(path: string, body: unknown, lang: string): Promise<T> {
  const res = await signedFetch(path, lang, {
    method: "POST",
    body: JSON.stringify(body),
  });
  return parse<T>(res);
}
