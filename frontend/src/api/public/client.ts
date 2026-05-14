import { tryMockPublicGet, tryMockPublicPost } from "./mockPublicData";

const API_BASE = (import.meta.env.VITE_API_BASE || "").trim().replace(/\/$/, "");

type Envelope<T> = { code: number; message: string; data: T };

async function parse<T>(res: Response): Promise<T> {
  let j: Envelope<T> & { detail?: unknown };
  try {
    j = (await res.json()) as Envelope<T> & { detail?: unknown };
  } catch {
    throw new Error(`HTTP ${res.status}（响应非 JSON）`);
  }
  if (!res.ok || j.code !== 0) {
    let msg = typeof j.message === "string" && j.message.trim() ? j.message.trim() : "";
    if (!msg && j.detail != null) {
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    }
    throw new Error(msg || `HTTP ${res.status}`);
  }
  return j.data;
}

export async function publicGet<T>(path: string): Promise<T> {
  const mocked = tryMockPublicGet<T>(path);
  if (mocked != null) return mocked;

  const url = path.startsWith("http") ? path : `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
  const res = await fetch(url);
  return parse<T>(res);
}

export async function publicPost<T>(path: string, body: unknown): Promise<T> {
  const mocked = tryMockPublicPost<T>(path, body);
  if (mocked != null) return mocked;

  const url = path.startsWith("http") ? path : `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  return parse<T>(res);
}
