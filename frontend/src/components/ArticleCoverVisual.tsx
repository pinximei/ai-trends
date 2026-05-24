import { useState } from "react";
import { articleCardInitial, articleThumbGradientStyle } from "@/articleCardVisual";

type Props = {
  coverUrl?: string | null;
  title: string;
  seed: string;
  /** 无图时：initial=标题首字；pattern=仅渐变纹理（首页卡片推荐） */
  fallbackMode?: "initial" | "pattern";
  /** 无图时的容器 class */
  fallbackClassName?: string;
  /** 有图时的 img class */
  imgClassName?: string;
  initialClassName?: string;
};

export function ArticleCoverVisual({
  coverUrl,
  title,
  seed,
  fallbackMode = "initial",
  fallbackClassName = "",
  imgClassName = "h-full w-full object-cover",
  initialClassName = "select-none text-2xl font-black text-white drop-shadow-md",
}: Props) {
  const [failed, setFailed] = useState(false);
  const url = (coverUrl || "").trim();
  if (url && !failed) {
    return (
      <img
        src={url}
        alt=""
        className={imgClassName}
        loading="lazy"
        decoding="async"
        referrerPolicy="no-referrer"
        onError={() => setFailed(true)}
      />
    );
  }
  return (
    <div
      className={`relative flex items-center justify-center overflow-hidden ${fallbackClassName}`}
      style={articleThumbGradientStyle(seed)}
      aria-hidden
    >
      <div
        className="pointer-events-none absolute inset-0 opacity-40"
        style={{
          backgroundImage:
            "radial-gradient(circle at 20% 30%, rgba(255,255,255,0.45) 0%, transparent 42%), radial-gradient(circle at 80% 70%, rgba(255,255,255,0.2) 0%, transparent 38%)",
        }}
      />
      {fallbackMode === "initial" ? (
        <span className={`relative z-[1] ${initialClassName}`}>{articleCardInitial(title)}</span>
      ) : null}
    </div>
  );
}
