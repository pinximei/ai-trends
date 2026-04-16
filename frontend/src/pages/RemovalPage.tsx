import { type FormEvent, useState } from "react";
import { apiGet, apiPost } from "@/api";
import { useI18n } from "@/i18n";
import { BadgeCheck, ShieldAlert } from "lucide-react";

export function RemovalPage() {
  const { lang, t } = useI18n();
  const [contact, setContact] = useState("");
  const [sid, setSid] = useState("sig_001");
  const [reason, setReason] = useState("");
  const [done, setDone] = useState<{ ticket_id: string; token: string } | null>(null);
  const [lookupTicket, setLookupTicket] = useState("");
  const [lookupToken, setLookupToken] = useState("");
  const [lookupStatus, setLookupStatus] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [lookupErr, setLookupErr] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    try {
      const data = await apiPost<{ ticket_id: string; token: string; status: string }>(
        "/api/v1/compliance/removal-requests",
        { requester_contact: contact, target_signal_id: sid, reason },
        lang
      );
      setDone({ ticket_id: data.ticket_id, token: data.token });
    } catch (e) {
      setErr(e instanceof Error ? e.message : "error");
    }
  }

  async function queryStatus(e: FormEvent) {
    e.preventDefault();
    setLookupErr(null);
    setLookupStatus(null);
    try {
      const data = await apiGet<{ ticket_id: string; status: string }>(
        `/api/v1/compliance/removal-requests/${encodeURIComponent(lookupTicket)}?token=${encodeURIComponent(lookupToken)}`,
        lang
      );
      setLookupStatus(data.status);
    } catch (e) {
      setLookupErr(e instanceof Error ? e.message : "error");
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <div className="grid gap-6 lg:grid-cols-12">
        <section className="rounded-3xl border border-white/10 bg-gradient-to-br from-slate-900/90 to-black/80 p-6 lg:col-span-5">
          <h1 className="text-gradient text-2xl font-bold">{t("removalTitle")}</h1>
          <p className="mt-3 text-sm text-slate-300">{t("removalHint")}</p>
          <div className="mt-6 space-y-3 text-sm">
            <div className="flex items-start gap-2 text-slate-300">
              <BadgeCheck className="mt-0.5 h-4 w-4 text-emerald-300" />
              {lang === "zh" ? "提交后生成工单号与查询令牌" : "Ticket id and token are generated after submit"}
            </div>
            <div className="flex items-start gap-2 text-slate-300">
              <BadgeCheck className="mt-0.5 h-4 w-4 text-emerald-300" />
              {lang === "zh" ? "支持后续状态查询与审计留痕" : "Supports follow-up tracking and audit trail"}
            </div>
            <div className="flex items-start gap-2 text-amber-200">
              <ShieldAlert className="mt-0.5 h-4 w-4 text-amber-300" />
              {lang === "zh" ? "请尽量填写可核验的理由与证据链接" : "Provide verifiable reason and evidence links when possible"}
            </div>
          </div>
        </section>
        <div className="lg:col-span-7" />
      </div>
      {done ? (
        <RemovalDone ticket={done.ticket_id} token={done.token} t={t} />
      ) : (
        <form onSubmit={submit} className="glass space-y-4 rounded-3xl p-8">
          <label className="block text-sm text-slate-400">
            {t("contact")}
            <input
              className="mt-1 w-full rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-white outline-none focus:border-rose-400/50"
              value={contact}
              onChange={(e) => setContact(e.target.value)}
              required
              type="email"
              placeholder="you@example.com"
            />
            <p className="mt-1 text-xs text-slate-500">
              {lang === "zh"
                ? "仅用于通知工单状态，不公开、不用于营销。"
                : "Used only for ticket status updates, never public or marketing."}
            </p>
          </label>
          <label className="block text-sm text-slate-400">
            {t("targetId")}
            <input
              className="mt-1 w-full rounded-xl border border-white/10 bg-black/30 px-4 py-3 font-mono text-sm text-white"
              value={sid}
              onChange={(e) => setSid(e.target.value)}
              required
            />
            <p className="mt-1 text-xs text-slate-500">
              {lang === "zh"
                ? "可在灵感/证据页面查看 signal ID，例如 sig_001。"
                : "Find signal ID on inspiration/evidence pages, e.g. sig_001."}
            </p>
          </label>
          <label className="block text-sm text-slate-400">
            {t("reason")}
            <textarea
              className="mt-1 w-full rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-white outline-none focus:border-rose-400/50"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              required
              rows={4}
            />
          </label>
          {err && <p className="text-sm text-rose-400">{err}</p>}
          <button
            type="submit"
            className="w-full rounded-xl bg-gradient-to-r from-rose-500 to-orange-500 py-3 font-semibold text-white shadow-lg"
          >
            {t("submit")}
          </button>
        </form>
      )}
      <form onSubmit={queryStatus} className="glass space-y-3 rounded-3xl p-8">
        <h2 className="text-base font-semibold text-white">{lang === "zh" ? "查询工单状态" : "Check ticket status"}</h2>
        <div className="grid gap-3 md:grid-cols-2">
          <input
            className="w-full rounded-xl border border-white/10 bg-black/30 px-4 py-3 font-mono text-sm text-white"
            placeholder={lang === "zh" ? "工单 ID" : "Ticket ID"}
            value={lookupTicket}
            onChange={(e) => setLookupTicket(e.target.value)}
            required
          />
          <input
            className="w-full rounded-xl border border-white/10 bg-black/30 px-4 py-3 font-mono text-sm text-white"
            placeholder={lang === "zh" ? "查询令牌" : "Token"}
            value={lookupToken}
            onChange={(e) => setLookupToken(e.target.value)}
            required
          />
        </div>
        <button
          type="submit"
          className="rounded-xl border border-cyan-500/30 bg-cyan-500/10 px-4 py-2 text-sm font-medium text-cyan-200 hover:bg-cyan-500/20"
        >
          {lang === "zh" ? "查询状态" : "Check status"}
        </button>
        {lookupStatus ? <p className="text-sm text-emerald-300">{lang === "zh" ? "当前状态：" : "Current status:"} {lookupStatus}</p> : null}
        {lookupErr ? <p className="text-sm text-rose-400">{lookupErr}</p> : null}
      </form>
    </div>
  );
}

function RemovalDone({ ticket, token, t }: { ticket: string; token: string; t: (k: string) => string }) {
  return (
    <div className="glass rounded-3xl p-8 text-slate-200">
      <p className="font-semibold text-emerald-400">{t("ticketCreated")}</p>
      <p className="mt-4 font-mono text-sm">
        ID: {ticket}
      </p>
      <p className="mt-2 text-sm text-slate-400">{t("copyToken")}</p>
      <p className="mt-1 break-all font-mono text-xs text-amber-200/90">{token}</p>
    </div>
  );
}
