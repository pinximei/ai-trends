"""每日订阅邮件：汇总当日已发布文章 → LLM 生成摘要 → 落库 → SMTP（按后台配置）。"""
from __future__ import annotations

import json
import logging
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


def _fetch_articles_for_day_lane(
    db: Session,
    d: date,
    *,
    feed_kind: str,
    limit: int,
    industry_ids: list[int],
) -> list[Article]:
    start_utc, end_utc = utc_naive_bounds_for_shanghai_date(d)
    if not industry_ids:
        return []
    lim = max(1, min(40, int(limit)))
    fk = (feed_kind or "news").strip().lower()
    q = (
        select(Article)
        .where(
            Article.industry_id.in_(industry_ids),
            Article.status == "published",
            Article.published_at.is_not(None),
            Article.published_at >= start_utc,
            Article.published_at < end_utc,
            Article.feed_kind == fk,
        )
        .order_by(Article.heat_score.desc(), Article.published_at.desc())
        .limit(lim)
    )
    return list(db.scalars(q).all())


def fetch_articles_for_shanghai_day(db: Session, d: date, *, limit: int) -> list[Article]:
    """兼容旧调用：合并应用与资讯，按发布时间排序。"""
    apps, news = fetch_articles_for_shanghai_day_split(
        db,
        d,
        apps_limit=max(1, limit // 2),
        news_limit=max(1, limit - max(1, limit // 2)),
    )
    merged = apps + news
    merged.sort(key=lambda a: (a.published_at or datetime.min), reverse=True)
    return merged[: max(1, min(80, int(limit)))]


def fetch_articles_for_shanghai_day_split(
    db: Session,
    d: date,
    *,
    apps_limit: int,
    news_limit: int,
) -> tuple[list[Article], list[Article]]:
    ids_ = _ai_industry_ids(db)
    apps = _fetch_articles_for_day_lane(db, d, feed_kind="apps", limit=apps_limit, industry_ids=ids_)
    news = _fetch_articles_for_day_lane(db, d, feed_kind="news", limit=news_limit, industry_ids=ids_)
    return apps, news


def _article_lines(articles: list[Article], *, heading: str) -> list[str]:
    lines: list[str] = [heading, ""]
    if not articles:
        lines.append("（本栏当日无新稿）")
        lines.append("")
        return lines
    for i, a in enumerate(articles, 1):
        title = (a.title or "").strip().replace("\n", " ")
        summ = (a.summary or "").strip().replace("\n", " ")
        tier = (a.replication_tier or "").strip()
        if len(summ) > 420:
            summ = summ[:418] + "…"
        tier_s = f" | 复刻{tier}" if tier else ""
        lines.append(f"{i}. id={a.id} | {title}{tier_s}")
        lines.append(f"   摘要：{summ or '（无摘要）'}")
        lines.append("")
    return lines


def _build_llm_user_payload(
    apps: list[Article],
    news: list[Article],
    digest_key: str,
) -> str:
    lines: list[str] = [
        f"日期（上海时区日历日）：{digest_key}",
        "",
        "请为订阅用户写「今日精选」：分 **AI 应用（可安装/可复刻产品）** 与 **AI 资讯** 两栏，突出值得跟进的条目。",
        "",
    ]
    lines.extend(_article_lines(apps, heading="## AI 应用（feed=apps）"))
    lines.extend(_article_lines(news, heading="## AI 资讯（feed=news）"))
    if not apps and not news:
        lines.append(
            "（当日两栏均无新稿，仍请写简短简报：说明今日无稿或可关注站内历史精选，语气友好，2～4 段即可）"
        )
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


def _digest_delivery_complete(row: NewsletterDailyDigest, settings: dict[str, Any]) -> bool:
    email_needed = bool(settings.get("send_enabled")) and _smtp_config_from_settings(settings)
    feishu_needed = bool(settings.get("feishu_enabled")) and bool((settings.get("feishu_webhook_url") or "").strip())
    if email_needed and row.sent_at is None:
        return False
    if feishu_needed and row.feishu_sent_at is None:
        return False
    if not email_needed and not feishu_needed:
        return row.status == "ready"
    return True


def generate_digest_content(
    db: Session,
    *,
    digest_date: str,
    apps: list[Article],
    news: list[Article],
    settings: dict[str, Any],
) -> None:
    """调用 LLM 写入 subject / body_md / article_ids_json；失败则 status=failed。"""
    row = _get_or_create_digest(db, digest_date)
    if _digest_delivery_complete(row, settings):
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
        "你是独立开发者向的 AI 产品情报站编辑，为订阅用户写「今日精选」简报。"
        "必须严格输出一个 JSON 对象，不要 Markdown 围栏，不要多余说明。"
        '键：subject（字符串，标题，中文，60字以内）、body_md（字符串，正文 Markdown，'
        "必须含「## 今日应用」与「## 今日资讯」两栏，各栏用要点列表；可引用文章 id；"
        "应用栏侧重可复刻/商业灵感，资讯栏侧重行业动态；语气专业友好。"
    )
    user = _build_llm_user_payload(apps, news, digest_date)
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
    row.article_ids_json = json.dumps(
        {"apps": [a.id for a in apps], "news": [a.id for a in news]},
        ensure_ascii=False,
    )
    row.input_token_count = it
    row.output_token_count = ot
    row.model_used = model
    row.status = "ready"
    row.error_message = None
    db.commit()


def send_digest_to_feishu(db: Session, *, digest_date: str, settings: dict[str, Any], apps_count: int, news_count: int) -> None:
    from ..newsletter_feishu import send_daily_digest_feishu

    row = db.scalar(select(NewsletterDailyDigest).where(NewsletterDailyDigest.digest_date == digest_date))
    if not row or not row.body_md or not row.subject:
        raise RuntimeError("digest 无正文，无法推送飞书")
    if row.feishu_sent_at is not None:
        return
    if not settings.get("feishu_enabled", False):
        raise RuntimeError("后台已关闭「飞书推送」")
    webhook = str(settings.get("feishu_webhook_url") or "").strip()
    if not webhook:
        raise RuntimeError("未配置飞书 Webhook URL")
    public_base = str(settings.get("public_site_base_url") or "").strip()
    send_daily_digest_feishu(
        webhook_url=webhook,
        digest_date=digest_date,
        subject=row.subject,
        body_md=row.body_md,
        public_site_base_url=public_base,
        apps_count=apps_count,
        news_count=news_count,
    )
    row.feishu_sent_at = datetime.utcnow()
    if row.status != "sent":
        row.status = "sent"
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


def run_daily_newsletter_digest_job(
    db: Session | None = None,
    settings: dict[str, Any] | None = None,
    *,
    digest_date: str | None = None,
    force: bool = False,
    regenerate: bool = False,
) -> dict[str, Any]:
    """
    定时/手动：上海日历日摘要；按 newsletter 配置生成并推送邮件与/或飞书。
    force=True 时忽略「已全部送达」跳过（用于后台手动重试）。
    regenerate=True 时强制重新生成正文（保留未发送渠道可再发）。
    """
    own_session = db is None
    db = db or SessionLocal()
    try:
        if settings is None:
            settings = get_newsletter_settings_merged(db)
        if not settings.get("daily_digest_job_enabled", True) and not force:
            return {"skipped": True, "reason": "daily_digest_job_disabled"}
        if not settings.get("cron_enabled", True) and not force:
            return {"skipped": True, "reason": "cron_disabled"}

        d = date.fromisoformat(digest_date) if digest_date else shanghai_calendar_today()
        digest_key = d.isoformat()
        row = db.scalar(select(NewsletterDailyDigest).where(NewsletterDailyDigest.digest_date == digest_key))
        if row and _digest_delivery_complete(row, settings) and not force and not regenerate:
            return {"skipped": True, "reason": "already_delivered", "digest_date": digest_key}

        apps_limit = int(settings.get("apps_limit") or 12)
        news_limit = int(settings.get("news_limit") or 12)
        apps, news = fetch_articles_for_shanghai_day_split(db, d, apps_limit=apps_limit, news_limit=news_limit)

        need_generate = (
            regenerate
            or not row
            or not (row.body_md or "").strip()
            or row.status == "failed"
        )
        if need_generate:
            if regenerate and row:
                row.body_md = ""
                row.subject = ""
                row.status = "pending"
                row.sent_at = None
                row.feishu_sent_at = None
                row.error_message = None
                db.commit()
            generate_digest_content(
                db,
                digest_date=digest_key,
                apps=apps,
                news=news,
                settings=settings,
            )
            db.expire_all()
            row = db.scalar(select(NewsletterDailyDigest).where(NewsletterDailyDigest.digest_date == digest_key))
        if not row or row.status != "ready" or not (row.body_md or "").strip():
            return {
                "digest_date": digest_key,
                "ok": False,
                "status": getattr(row, "status", "missing") if row else "missing",
                "error": getattr(row, "error_message", None) if row else None,
            }

        out: dict[str, Any] = {
            "digest_date": digest_key,
            "ok": True,
            "generated": True,
            "apps_count": len(apps),
            "news_count": len(news),
            "email_sent": False,
            "feishu_sent": False,
        }

        if settings.get("send_enabled", True) and _smtp_config_from_settings(settings):
            if row.sent_at is None:
                try:
                    send_digest_to_subscribers(db, digest_date=digest_key, settings=settings)
                    out["email_sent"] = True
                except Exception as e:
                    logger.exception("newsletter daily email send failed: %s", e)
                    r2 = db.scalar(select(NewsletterDailyDigest).where(NewsletterDailyDigest.digest_date == digest_key))
                    if r2:
                        r2.error_message = f"email: {e}"[:2000]
                        db.commit()
                    return {**out, "ok": False, "error": str(e)}
            else:
                out["email_sent"] = True
        elif settings.get("send_enabled", True):
            logger.warning("newsletter daily: SMTP incomplete, digest_date=%s", digest_key)
            out["email_skip"] = "no_smtp"

        feishu_on = bool(settings.get("feishu_enabled")) and bool((settings.get("feishu_webhook_url") or "").strip())
        if feishu_on:
            db.expire_all()
            row = db.scalar(select(NewsletterDailyDigest).where(NewsletterDailyDigest.digest_date == digest_key))
            if row and row.feishu_sent_at is None:
                try:
                    send_digest_to_feishu(
                        db,
                        digest_date=digest_key,
                        settings=settings,
                        apps_count=len(apps),
                        news_count=len(news),
                    )
                    out["feishu_sent"] = True
                except Exception as e:
                    logger.exception("newsletter daily feishu send failed: %s", e)
                    r2 = db.scalar(select(NewsletterDailyDigest).where(NewsletterDailyDigest.digest_date == digest_key))
                    if r2:
                        prev = (r2.error_message or "").strip()
                        r2.error_message = f"{prev}; feishu: {e}"[:2000].strip("; ")
                        db.commit()
                    return {**out, "ok": False, "error": str(e)}
            else:
                out["feishu_sent"] = True

        out["sent"] = bool(out.get("email_sent")) or bool(out.get("feishu_sent"))
        return out
    finally:
        if own_session:
            db.close()


def digest_row_public(row: NewsletterDailyDigest | None) -> dict[str, Any] | None:
    if not row:
        return None
    try:
        ids = json.loads(row.article_ids_json or "{}")
    except json.JSONDecodeError:
        ids = row.article_ids_json
    return {
        "digest_date": row.digest_date,
        "subject": row.subject,
        "body_md": row.body_md,
        "status": row.status,
        "error_message": row.error_message,
        "article_ids": ids,
        "sent_at": row.sent_at.isoformat() if row.sent_at else None,
        "feishu_sent_at": row.feishu_sent_at.isoformat() if row.feishu_sent_at else None,
        "model_used": row.model_used,
    }
