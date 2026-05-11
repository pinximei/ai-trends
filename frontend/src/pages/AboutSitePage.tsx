import { useEffect, useState } from "react";
import { publicApi } from "@/api/public";
import { useI18n } from "@/i18n";

export function AboutSitePage() {
  const { t, lang } = useI18n();
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    setErr("");
    publicApi
      .page("about", { lang })
      .then((p) => {
        setTitle(p.title);
        setBody(p.body_md);
      })
      .catch((e) => setErr(String(e)));
  }, [lang]);

  return (
    <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <div className="glass-light p-5 sm:p-7">
        <h1 className="text-xl font-bold tracking-tight text-slate-900 sm:text-2xl">{t("navAbout")}</h1>
        {err ? <p className="mt-4 text-sm font-medium text-rose-600">{err}</p> : null}
        {!err && (title || body) ? (
          <div className="mt-6 rounded-3xl border border-slate-100 bg-slate-50/60 p-6 sm:p-8">
            <div className="mx-auto max-w-3xl">
              {title ? <h2 className="text-xl font-bold tracking-tight text-slate-900 sm:text-2xl">{title}</h2> : null}
              <div
                className={`max-w-none whitespace-pre-wrap text-slate-600 [&_a]:font-medium [&_a]:text-violet-600 hover:[&_a]:underline ${title ? "mt-6" : ""}`}
              >
                {body}
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
