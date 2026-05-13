import type { CSSProperties } from "react";

/** 列表卡片左侧色块：由条目 id+标题 决定渐变，每条不同、两页共用同一套规则 */
export function articleThumbGradientStyle(seed: string): CSSProperties {
  let n = 0;
  for (let i = 0; i < seed.length; i++) n += seed.charCodeAt(i);
  const hue = (n * 47) % 360;
  const hue2 = (hue + 38) % 360;
  return {
    background: `linear-gradient(135deg, hsl(${hue} 72% 52%) 0%, hsl(${hue2} 65% 42%) 100%)`,
  };
}

/** 卡片主标识字：取标题首字符（每条不同） */
export function articleCardInitial(title: string): string {
  const s = (title || "").trim();
  if (!s) return "?";
  return s.slice(0, 1);
}
