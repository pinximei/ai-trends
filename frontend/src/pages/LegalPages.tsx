import { useI18n } from "@/i18n";
import { FileText } from "lucide-react";
import { Link } from "react-router-dom";

function LegalShell({ title, body, lang }: { title: string; body: string; lang: "zh" | "en" }) {
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <header className="rounded-3xl border border-white/10 bg-gradient-to-br from-slate-900/95 via-slate-950/85 to-black/90 p-8">
        <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-black/20 px-3 py-1 text-xs text-slate-300">
          <FileText className="h-3.5 w-3.5 text-cyan-300" />
          {lang === "zh" ? "法律文档" : "Legal document"}
        </div>
        <h1 className="mt-4 text-gradient text-3xl font-bold">{title}</h1>
      </header>
      <article className="glass rounded-3xl p-8 text-slate-300">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
          {lang === "zh" ? "正文" : "Statement"}
        </h2>
        <p className="mt-3 leading-relaxed">{body}</p>
      </article>
    </div>
  );
}

export function LegalPrivacy() {
  const { lang } = useI18n();
  const title = lang === "zh" ? "隐私" : "Privacy";
  const body =
    lang === "zh"
      ? "运营方：AISoul 项目运营者。联系方式：legal@aisoul.local"
      : "Operator: AISoul Project Operator. Contact: legal@aisoul.local";
  return <LegalShell title={title} body={body} lang={lang} />;
}

export function LegalTerms() {
  const { lang } = useI18n();
  const title = lang === "zh" ? "条款" : "Terms";
  const body =
    lang === "zh"
      ? "适用法律：运营方注册地法律。争议解决：注册地有管辖权法院。"
      : "Applicable law: operator registration jurisdiction. Dispute: competent court of that jurisdiction.";
  return <LegalShell title={title} body={body} lang={lang} />;
}

export function LegalSources() {
  const { lang } = useI18n();
  const title = lang === "zh" ? "数据来源" : "Data sources";
  const body =
    lang === "zh"
      ? "GitHub、Hugging Face、Hacker News、Product Hunt、Reddit、MCP/Skills 索引。"
      : "GitHub, Hugging Face, Hacker News, Product Hunt, Reddit, MCP/Skills indexes.";
  return <LegalShell title={title} body={body} lang={lang} />;
}

export function LegalHub() {
  const { lang } = useI18n();
  const cards = [
    {
      to: "/legal/removal-request",
      title: lang === "zh" ? "删除 / 纠错申请" : "Removal / correction request",
      desc: lang === "zh" ? "提交工单并获取查询令牌。" : "Submit ticket and get query token.",
    },
    {
      to: "/legal/privacy",
      title: lang === "zh" ? "隐私" : "Privacy",
      desc: lang === "zh" ? "查看联系方式与处理说明。" : "View contact and policy notes.",
    },
    {
      to: "/legal/terms",
      title: lang === "zh" ? "条款" : "Terms",
      desc: lang === "zh" ? "查看适用法律与争议处理。" : "Review applicable law and dispute handling.",
    },
    {
      to: "/legal/data-sources",
      title: lang === "zh" ? "数据来源" : "Data sources",
      desc: lang === "zh" ? "查看公开生态来源列表。" : "Review public ecosystem sources.",
    },
  ];

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <header className="rounded-3xl border border-white/10 bg-gradient-to-br from-slate-900/95 via-slate-950/85 to-black/90 p-8">
        <h1 className="text-gradient text-3xl font-bold">{lang === "zh" ? "合规中心" : "Compliance hub"}</h1>
        <p className="mt-3 text-sm text-slate-300">
          {lang === "zh" ? "统一处理法务说明、数据透明和删除纠错申请。" : "Central place for legal notes, data transparency, and removal workflow."}
        </p>
      </header>
      <div className="grid gap-4 md:grid-cols-2">
        {cards.map((c) => (
          <Link key={c.to} to={c.to} className="glass glass-hover rounded-2xl p-5">
            <h2 className="text-lg font-semibold text-white">{c.title}</h2>
            <p className="mt-2 text-sm text-slate-300">{c.desc}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
