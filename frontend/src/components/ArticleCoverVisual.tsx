import { useState } from "react";
import { articleCardInitial, articleThumbGradientStyle } from "@/articleCardVisual";

type Props = {
  coverUrl?: string | null;
  title: string;
  seed: string;
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
    <div className={fallbackClassName} style={articleThumbGradientStyle(seed)} aria-hidden>
      <span className={initialClassName}>{articleCardInitial(title)}</span>
    </div>
  );
}
