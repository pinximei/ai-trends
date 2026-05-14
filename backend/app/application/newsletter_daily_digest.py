"""每日订阅邮件：汇总当日已发布文章 → LLM 生成摘要 → 落库 → SMTP（按后台配置）。"""
from __future__ import annotations

import json
import logging
import os
import re
import smtplib
import ssl
import time
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..application.article_public import _public_industry_ids_for_slug
from ..db import SessionLocal
from ..llm_service import chat_completion
from ..llm_settings_service import resolve_llm_http_config
from ..models import NewsletterDailyDigest, NewsletterSubscriber
from ..newsletter_settings_service import get_newsletter_settings_merged
from ..product_models import Article, Industry

logger = logging.getLogger(__name__)

_SH_TZ = ZoneInfo("Asia/Shanghai")


def shanghai_calendar_today() -> date:
    return datetime.now(_SH_TZ).date()


def utc_naive_bounds_for_shanghai_date(d: date) -> tuple[datetime, datetime]:
    """与库内 naive UTC `published_at` 对齐的区间 [start, end)。"""
    start_local = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=_SH_TZ)
    end_local = start_local + timedelta(days=1)
    return (
        start_local.astimezone(timezone.utc).replace(tzinfo=None),
        end_local.astimezone(timezone.utc).replace(tzinfo=None),
    )


def _ai_industry_ids(db: Session) -> list[int]:
    ind = db.scalar(select(Industry).where(Industry.slug == "ai"))
    if not ind:
        return []
    return _public_industry_ids_for_slug(db, ind)


def fetch_articles_for_shanghai_day(db: Session, d: date, *, limit: int) -> list[Article]:
    start_utc, end_utc = utc_naive_bounds_for_shanghai_date(d)
    ids_ = _ai_industry_ids(db)
    if not ids_:
        return []
    lim = max(1, min(80, int(limit)))
    q = (
        select(Article)
        .where(
            Article.industry_id.in_(ids_),
            Article.status == "published",
            Article.published_at.is_not(None),
            Article.published_at >= start_utc,
            Article.published_at < end_utc,
        )
        .order_by(Article.published_at.desc())
        .limit(lim)
    )
    return list(db.scalars(q).all())


def _build_llm_user_payload(articles: list[Article], digest_key: str) -> str:
    lines: list[str] = [f"日期（上海时区日历日）：{digest_key}", "", "以下为当日已发布文章（标题与摘要），请生成订阅邮件内容：", ""]
    for i, a in enumerate(articles, 1):
        title = (a.title or "").strip().replace("\n", " ")
        summ = (a.summary or "").strip().replace("\n", " ")
        if len(summ) > 420:
            summ = summ[:418] + "…"
        lines.append(f"{i}. id={a.id} | {title}")
        lines.append(f"   摘要：{summ or '（无摘要）'}")
        lines.append("")
    if not articles:
        lines.append("（当日无新发布文章，仍请写一封简短简报：说明今日无稿或可关注站内历史精选，语气友好，2～4 段即可）")
    return "\n".join(lines)


def _parse_digest_json(raw: str) -> tuple[str, str] | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", s)
        if not m:
            return None
        try:
            obj = json.loads(m.group())
        except json.JSONDecodeError:
            return None
    if not isinstance(obj, dict):
        return None
    subj = str(obj.get("subject") or "").strip()
    body = str(obj.get("body_md") or "").strip()
    if not subj or not body:
        return None
    if len(subj) > 200:
        subj = subj[:198] + "…"
    return subj, body


def _md_to_plain(md: str) -> str:
    t = (md or "").strip()
    t = re.sub(r"^#+\s*", "", t, flags=re.MULTILINE)
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    return t


def _smtp_config_from_settings(s: dict[str, Any]) -> dict[str, Any] | None:
    host = str(s.get("smtp_host") or "").strip()
    if not host:
        return None
    mail_from = str(s.get("mail_from") or "").strip() or str(s.get("smtp_user") or "").strip()
    if not mail_from:
        return None
    return {
        "host": host,
        "port": int(s.get("smtp_port") or 465),
        "user": str(s.get("smtp_user") or "").strip(),
        "password": str(s.get("smtp_password") or "").strip(),
        "mail_from": mail_from,
        "use_tls": bool(s.get("smtp_use_tls")),
    }


def _smtp_send_loop(
    cfg: dict[str, Any],
    *,
    recipients: list[tuple[str, str]],
    subject: str,
    body_common: str,
    public_base: str,
    footer_note: str,
) -> None:
    """recipients: (email, unsubscribe_token)。每封单独 To，附带退订链接。"""
    if not recipients:
        raise RuntimeError("无收件人")
    base = public_base.rstrip("/")
    if not base:
        raise RuntimeError("未配置 public_site_base_url，无法生成退订链接")
    ctx = ssl.create_default_context()
    port = int(cfg["port"])
    host = str(cfg["host"])

    def _one(smtp_conn: smtplib.SMTP_SSL | smtplib.SMTP, to_addr: str, token: str) -> None:
        extra = (footer_note.strip() + "\n\n") if footer_note.strip() else ""
        unsub = f"{base}/api/public/v1/newsletter/unsubscribe?token={token}"
        foot = f"\n\n---\n{extra}退订本邮件订阅：{unsub}\n"
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = cfg["mail_from"]
        msg["To"] = to_addr
        msg.set_content(body_common + foot, subtype="plain", charset="utf-8")
        smtp_conn.send_message(msg)

    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx) as smtp:
            if cfg["user"] and cfg["password"]:
                smtp.login(str(cfg["user"]), str(cfg["password"]))
            for to_addr, tok in recipients:
                _one(smtp, to_addr, tok)
                time.sleep(0.03)
    else:
        with smtplib.SMTP(host, port, timeout=90) as smtp:
            if cfg["use_tls"] or port == 587:
                smtp.starttls(context=ctx)
            if cfg["user"] and cfg["password"]:
                smtp.login(str(cfg["user"]), str(cfg["password"]))
            for to_addr, tok in recipients:
                _one(smtp, to_addr, tok)
                time.sleep(0.03)


def _get_or_create_digest(db: Session, digest_date: str) -> NewsletterDailyDigest:
    row = db.scalar(select(NewsletterDailyDigest).where(NewsletterDailyDigest.digest_date == digest_date))
    if row:
        return row
    row = NewsletterDailyDigest(digest_date=digest_date, status="pending")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def generate_digest_content(db: Session, *, digest_date: str, articles: list[Article], settings: dict[str, Any]) -> None:
    """调用 LLM 写入 subject / body_md / article_ids_json；失败则 status=failed。"""
    row = _get_or_create_digest(db, digest_date)
    if row.sent_at is not None:
        return
    if not settings.get("generate_enabled", True):
        row.status = "failed"
        row.error_message = "后台已关闭「生成摘要」"
        db.commit()
        return
    if not resolve_llm_http_config(db)[1]:
        row.status = "failed"
        row.error_message = "LLM 未配置，无法生成摘要"
        db.commit()
        return
    system = (
        "你是 AI 科技资讯站的编辑，为邮件订阅用户写「今日精选」简报。"
        "必须严格输出一个 JSON 对象，不要 Markdown 围栏，不要多余说明。"
        '键：subject（字符串，邮件标题，中文，60字以内）、body_md（字符串，正文 Markdown，'
        "含二级标题与要点列表，可含文章 id 引用；语气专业友好，适合中文读者）。"
    )
    user = _build_llm_user_payload(articles, digest_date)
    raw, it, ot = chat_completion(
        db,
        system=system,
        user=user,
        scenario="newsletter_daily_digest",
        ref_type="newsletter_daily_digest",
        ref_id=digest_date,
        response_json=True,
        max_tokens=4096,
    )
    parsed = _parse_digest_json(raw)
    if not parsed:
        row.status = "failed"
        row.error_message = "模型返回非预期 JSON"
        row.input_token_count = it
        row.output_token_count = ot
        db.commit()
        return
    subj, body_md = parsed
    _base, _key, model = resolve_llm_http_config(db)
    row.subject = subj
    row.body_md = body_md
    row.article_ids_json = json.dumps([a.id for a in articles], ensure_ascii=False)
    row.input_token_count = it
    row.output_token_count = ot
    row.model_used = model
    row.status = "ready"
    row.error_message = None
    db.commit()


def send_digest_to_subscribers(db: Session, *, digest_date: str, settings: dict[str, Any]) -> None:
    row = db.scalar(select(NewsletterDailyDigest).where(NewsletterDailyDigest.digest_date == digest_date))
    if not row or not row.body_md or not row.subject:
        raise RuntimeError("digest 无正文，无法发送")
    if row.sent_at is not None:
        return
    if not settings.get("send_enabled", True):
        raise RuntimeError("后台已关闭「发送邮件」")
    subs = list(
        db.scalars(
            select(NewsletterSubscriber).where(
                NewsletterSubscriber.unsubscribed_at.is_(None),
                NewsletterSubscriber.unsubscribe_token.is_not(None),
            )
        ).all()
    )
    if not subs:
        logger.info("newsletter daily: no active subscribers, digest_date=%s", digest_date)
        row.sent_at = datetime.utcnow()
        row.status = "sent"
        row.error_message = None
        db.commit()
        return
    cfg = _smtp_config_from_settings(settings)
    if not cfg:
        raise RuntimeError("SMTP 未配置完整（smtp_host / mail_from）")
    public_base = str(settings.get("public_site_base_url") or "").strip()
    if not public_base:
        raise RuntimeError("未配置 public_site_base_url（站点对外根 URL，用于退订链接）")
    plain = _md_to_plain(row.body_md)
    recipients = [(s.email, s.unsubscribe_token or "") for s in subs if s.unsubscribe_token]
    if not recipients:
        raise RuntimeError("订阅者缺少退订 token，请等待后台补全或重新订阅")
    footer_note = str(settings.get("footer_note") or "")
    _smtp_send_loop(cfg, recipients=recipients, subject=row.subject, body_common=plain, public_base=public_base, footer_note=footer_note)
    row.sent_at = datetime.utcnow()
    row.status = "sent"
    row.error_message = None
    db.commit()


def run_daily_newsletter_digest_job(db: Session | None = None, settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    定时任务：上海日历「今天」；按 product_settings_kv.newsletter 决定是否生成/发送。
    环境变量 NEWSLETTER_DAILY_ENABLED=0 仍可紧急关闭整条链路。
    """
    if (os.environ.get("NEWSLETTER_DAILY_ENABLED") or "").strip().lower() in ("0", "false", "no", "off"):
        return {"skipped": True, "reason": "NEWSLETTER_DAILY_ENABLED off"}
    own_session = db is None
    db = db or SessionLocal()
    try:
        if settings is None:
            settings = get_newsletter_settings_merged(db)
        if not settings.get("cron_enabled", True):
            return {"skipped": True, "reason": "cron_disabled"}

        d = shanghai_calendar_today()
        digest_key = d.isoformat()
        row = db.scalar(select(NewsletterDailyDigest).where(NewsletterDailyDigest.digest_date == digest_key))
        if row and row.sent_at is not None:
            return {"skipped": True, "reason": "already_sent", "digest_date": digest_key}

        article_limit = int(settings.get("article_limit") or 36)
        articles = fetch_articles_for_shanghai_day(db, d, limit=article_limit)
        if not row or not (row.body_md or "").strip() or row.status == "failed":
            generate_digest_content(db, digest_date=digest_key, articles=articles, settings=settings)
            db.expire_all()
            row = db.scalar(select(NewsletterDailyDigest).where(NewsletterDailyDigest.digest_date == digest_key))
        if not row or row.status != "ready" or not (row.body_md or "").strip():
            return {
                "digest_date": digest_key,
                "ok": False,
                "status": getattr(row, "status", "missing") if row else "missing",
                "error": getattr(row, "error_message", None) if row else None,
            }

        if not settings.get("send_enabled", True):
            logger.info("newsletter daily: send disabled in settings, digest_date=%s", digest_key)
            return {"digest_date": digest_key, "ok": True, "generated": True, "sent": False, "reason": "send_disabled"}

        if not _smtp_config_from_settings(settings):
            logger.warning("newsletter daily: SMTP incomplete in settings/env, digest_date=%s", digest_key)
            return {"digest_date": digest_key, "ok": True, "generated": True, "sent": False, "reason": "no_smtp"}

        try:
            send_digest_to_subscribers(db, digest_date=digest_key, settings=settings)
        except Exception as e:
            logger.exception("newsletter daily send failed: %s", e)
            r2 = db.scalar(select(NewsletterDailyDigest).where(NewsletterDailyDigest.digest_date == digest_key))
            if r2:
                r2.error_message = f"send: {e}"[:2000]
                db.commit()
            return {"digest_date": digest_key, "ok": False, "sent": False, "error": str(e)}

        return {"digest_date": digest_key, "ok": True, "generated": True, "sent": True}
    finally:
        if own_session:
            db.close()
