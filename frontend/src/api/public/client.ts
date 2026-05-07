import { apiGet } from "../signedClient";

const DEFAULT_LANG = "zh-CN";

export async function publicGet<T>(path: string): Promise<T> {
  return apiGet<T>(path, DEFAULT_LANG);
}
