import { useEffect, useState } from "react";
import { publicApi } from "@/lib/publicApi";
import { useI18n } from "@/i18n";

export function AboutSitePage() {
  const { t } = useI18n();
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    publicApi
      .page("about")
      .then((p) => {
        setTitle(p.title);
        setBody(p.body_md);
      })
      .catch((e) => setErr(String(e)));
  }, []);

  return (
    <div className="mx-auto max-w-3xl px-4 py-10 text-slate-200">
      <h1 className="text-2xl font-semibold text-white">{t("navAbout")}</h1>
      {err ? <p className="mt-4 text-red-400">{err}</p> : null}
      {title ? <h2 className="mt-8 text-xl text-white">{title}</h2> : null}
      <div className="prose prose-invert mt-6 max-w-none whitespace-pre-wrap text-slate-300">{body}</div>
    </div>
  );
}
