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
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..application.article_public import _article_matches_public_feed, _monetization_counts_as_apps_feed, _public_industry_ids_for_slug
from ..domain import articles as art
from ..db import SessionLocal
from ..llm_service import chat_completion
from ..llm_settings_service import resolve_llm_http_config
from ..models import NewsletterDailyDigest, NewsletterSubscriber
from ..newsletter_digest_format import (
    DIGEST_SUBJECT_LLM_SYSTEM,
    build_digest_body_from_articles,
    build_digest_subject_default,
    digest_delivery_texts,
    format_digest_for_delivery,
)
from ..newsletter_settings_service import get_newsletter_settings_merged
from ..product_models import Article, Industry
from ..us_content_calendar import US_TIMEZONE_LABEL, us_calendar_today, utc_naive_bounds_for_us_date

logger = logging.getLogger(__name__)


def shanghai_calendar_today() -> date:
    """兼容旧名：摘要日与摘要素材均按美东日历「当天」。"""
    return us_calendar_today()


def utc_naive_bounds_for_shanghai_date(d: date) -> tuple[datetime, datetime]:
    return utc_naive_bounds_for_us_date(d)


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
    start_utc, end_utc = utc_naive_bounds_for_us_date(d)
    if not industry_ids:
        return []
    lim = max(1, min(40, int(limit)))
    fk = (feed_kind or "news").strip().lower()
    base = (
        select(Article)
        .where(
            Article.industry_id.in_(industry_ids),
            Article.status == "published",
            Article.published_at.is_not(None),
            Article.published_at >= start_utc,
            Article.published_at < end_utc,
        )
        .order_by(Article.heat_score.desc(), Article.published_at.desc())
    )
    if fk == "apps":
        q = base.where(
            (Article.feed_kind == "apps")
            | (Article.third_party_source.ilike("github%"))
            | (Article.third_party_source.ilike("taaft%"))
            | (Article.third_party_source.ilike("acquire%"))
        ).limit(max(lim * 4, 32))
        from ..newsletter_replication import article_value_assessed

        rows = [
            a
            for a in db.scalars(q).all()
            if _article_matches_public_feed(a, "apps") and article_value_assessed(a)
        ]
        return _prioritize_digest_apps(rows)[:lim]
    q = base.where(Article.feed_kind == "news").limit(max(lim * 4, 24))
    rows = [a for a in db.scalars(q).all() if _article_matches_public_feed(a, "news")]
    return rows[:lim]


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


def _prioritize_digest_apps(articles: list[Article]) -> list[Article]:
    """邮件/飞书摘要应用栏：高价值评估优先，再变现向源/类，再按价值分与热度。"""
    from ..newsletter_replication import article_high_value_for_digest, article_replication_public

    def _rank(a: Article) -> tuple[int, int, int, int, int, float, int]:
        cats = art.display_categories_for_article(getattr(a, "ai_categories_json", None))
        primary = cats[0] if cats else ""
        high = 0 if article_high_value_for_digest(a) else 1
        repl = article_replication_public(a) or {}
        worth = -int(repl.get("worth_score") or 0)
        mon_src = 0 if art.admin_source_key(a.third_party_source) in art.MONETIZATION_SOURCE_KEYS else 1
        mon_cat = 0 if primary in art.MONETIZATION_APPS_CATEGORIES else 1
        heat = -float(getattr(a, "heat_score", None) or 0.0)
        aid = -int(a.id or 0)
        return (high, worth, mon_src, mon_cat, heat, aid)

    return sorted(articles, key=_rank)


def fetch_articles_for_shanghai_day_split(
    db: Session,
    d: date,
    *,
    apps_limit: int,
    news_limit: int,
) -> tuple[list[Article], list[Article]]:
    """美东日历「当天」已发布文章，按热度各取 Top N。"""
    return fetch_articles_for_us_date_range_split(
        db, d, d, apps_limit=apps_limit, news_limit=news_limit
    )


def fetch_articles_for_us_date_range_split(
    db: Session,
    start: date,
    end: date,
    *,
    apps_limit: int,
    news_limit: int,
) -> tuple[list[Article], list[Article]]:
    """美东日历闭区间 [start, end] 内已发布文章，按热度各取 Top N。"""
    if end < start:
        start, end = end, start
    ids_ = _ai_industry_ids(db)
    if not ids_:
        return [], []
    start_utc, _ = utc_naive_bounds_for_us_date(start)
    _, end_utc_excl = utc_naive_bounds_for_us_date(end)
    apps_lim = max(1, min(40, int(apps_limit)))
    news_lim = max(1, min(40, int(news_limit)))

    def _lane(feed_kind: str, lim: int) -> list[Article]:
        fk = (feed_kind or "news").strip().lower()
        base = (
            select(Article)
            .where(
                Article.industry_id.in_(ids_),
                Article.status == "published",
                Article.published_at.is_not(None),
                Article.published_at >= start_utc,
                Article.published_at < end_utc_excl,
            )
            .order_by(Article.heat_score.desc(), Article.published_at.desc())
        )
        if fk == "apps":
            q = base.where(
                (Article.feed_kind == "apps")
                | (Article.third_party_source.ilike("github%"))
                | (Article.third_party_source.ilike("taaft%"))
                | (Article.third_party_source.ilike("acquire%"))
            ).limit(max(lim * 4, 32))
            from ..newsletter_replication import article_value_assessed

            rows = [
                a
                for a in db.scalars(q).all()
                if _article_matches_public_feed(a, "apps") and article_value_assessed(a)
            ]
            return _prioritize_digest_apps(rows)[:lim]
        q = base.where(Article.feed_kind == "news").limit(max(lim * 4, 24))
        rows = [a for a in db.scalars(q).all() if _article_matches_public_feed(a, "news")]
        return rows[:lim]

    return _lane("apps", apps_lim), _lane("news", news_lim)


def _build_llm_subject_payload(
    apps: list[Article],
    news: list[Article],
    digest_key: str,
) -> str:
    """仅标题列表，供 LLM 写推送标题（极短 prompt）。"""
    lines = [f"日期：{digest_key}", "根据下列标题写推送 subject，勿写正文："]
    for a in apps:
        title = (a.title or "").strip().replace("\n", " ")[:48]
        lines.append(f"- 应用 #{a.id} {title}")
    for a in news:
        title = (a.title or "").strip().replace("\n", " ")[:48]
        lines.append(f"- 资讯 #{a.id} {title}")
    if not apps and not news:
        lines.append("（今日无新稿，标题可写「今日暂无更新」类简短说明）")
    return "\n".join(lines)


def _parse_subject_json(raw: str) -> str | None:
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
    if not subj:
        return None
    if len(subj) > 200:
        subj = subj[:198] + "…"
    return subj


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


_MIN_DIGEST_BODY_LEN = 400


def _digest_body_substantive(row: NewsletterDailyDigest | None) -> bool:
    """过短正文视为未成功推送（避免午后误触飞书后阻塞次日早间定时）。"""
    return bool(row and len((row.body_md or "").strip()) >= _MIN_DIGEST_BODY_LEN)


def _digest_delivery_complete(row: NewsletterDailyDigest, settings: dict[str, Any]) -> bool:
    from .newsletter_period_digest import normalize_feishu_cadence

    if row.status != "ready" or not _digest_body_substantive(row):
        return False
    email_needed = bool(settings.get("send_enabled")) and _smtp_config_from_settings(settings)
    feishu_cadence = normalize_feishu_cadence(settings.get("feishu_push_cadence"))
    feishu_needed = (
        feishu_cadence == "daily"
        and bool(settings.get("feishu_enabled"))
        and bool((settings.get("feishu_webhook_url") or "").strip())
    )
    if email_needed and row.sent_at is None:
        return False
    if feishu_needed and (row.feishu_sent_at is None or not _digest_body_substantive(row)):
        return False
    if not email_needed and not feishu_needed:
        return True
    return True


def _digest_has_content(row: NewsletterDailyDigest | None) -> bool:
    return bool(row and row.status == "ready" and _digest_body_substantive(row))


def _article_counts_from_row(row: NewsletterDailyDigest | None) -> tuple[int, int]:
    if not row:
        return 0, 0
    try:
        id_map = json.loads(row.article_ids_json or "{}")
        if isinstance(id_map, dict):
            return len(id_map.get("apps") or []), len(id_map.get("news") or [])
    except json.JSONDecodeError:
        pass
    return 0, 0


def generate_digest_content(
    db: Session,
    *,
    digest_date: str,
    apps: list[Article],
    news: list[Article],
    settings: dict[str, Any],
) -> None:
    """拼装正文（站内摘要）+ 可选 LLM 仅写标题；落库 subject / body_md（每个日历日一篇）。"""
    row = _get_or_create_digest(db, digest_date)
    if not settings.get("generate_enabled", True):
        row.status = "failed"
        row.error_message = "后台已关闭「生成摘要」"
        db.commit()
        return

    public_base = str(settings.get("public_site_base_url") or "").strip()
    hl_apps = max(0, min(8, int(settings.get("llm_apps_limit", 3))))
    hl_news = max(0, min(8, int(settings.get("llm_news_limit", 3))))
    from .home_public import _eligible_monetization_highlight

    mon_apps = [a for a in apps if _eligible_monetization_highlight(a)]
    reg_apps = [a for a in apps if a not in mon_apps]
    body_md = build_digest_body_from_articles(
        apps,
        news,
        highlight_apps=hl_apps,
        highlight_news=hl_news,
        monetization_apps=mon_apps,
        regular_apps=reg_apps,
    )
    subject = build_digest_subject_default(digest_date, apps, news)
    it, ot = 0, 0
    model: str | None = None

    llm_apps = max(0, min(8, int(settings.get("llm_apps_limit", 3))))
    llm_news = max(0, min(8, int(settings.get("llm_news_limit", 3))))
    _base, llm_key, model_resolved = resolve_llm_http_config(db)
    if (llm_apps or llm_news) and llm_key:
        user = _build_llm_subject_payload(apps[:llm_apps], news[:llm_news], digest_date)
        raw, it, ot, _ = chat_completion(
            db,
            system=DIGEST_SUBJECT_LLM_SYSTEM,
            user=user,
            scenario="newsletter_daily_digest",
            ref_type="newsletter_daily_digest",
            ref_id=digest_date,
            response_json=True,
            max_tokens=128,
        )
        subj_llm = _parse_subject_json(raw)
        if subj_llm:
            subject = subj_llm
        model = model_resolved

    body_md, _email_plain, _feishu = format_digest_for_delivery(
        body_md,
        subject,
        digest_date=digest_date,
        public_site_base_url=public_base,
        apps=apps,
        news=news,
    )
    row.subject = subject
    row.body_md = body_md
    row.article_ids_json = json.dumps(
        {"apps": [a.id for a in apps], "news": [a.id for a in news]},
        ensure_ascii=False,
    )
    row.input_token_count = it
    row.output_token_count = ot
    row.model_used = model or model_resolved
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
    _, feishu_text = digest_delivery_texts(
        row.body_md,
        row.subject,
        digest_date=digest_date,
        public_site_base_url=public_base,
        apps_count=apps_count,
        news_count=news_count,
    )
    send_daily_digest_feishu(webhook_url=webhook, text=feishu_text)
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
    try:
        id_map = json.loads(row.article_ids_json or "{}")
        apps_n = len(id_map.get("apps") or []) if isinstance(id_map, dict) else 0
        news_n = len(id_map.get("news") or []) if isinstance(id_map, dict) else 0
    except json.JSONDecodeError:
        apps_n, news_n = 0, 0
    plain, _ = digest_delivery_texts(
        row.body_md,
        row.subject,
        digest_date=digest_date,
        public_site_base_url=public_base,
        apps_count=apps_n,
        news_count=news_n,
    )
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
    manual_run: bool = False,
    regenerate: bool = False,
    push_only: bool = False,
    scheduled_run: bool = False,
) -> dict[str, Any]:
    """
    定时/手动：按美东日历日在 ``newsletter_daily_digests`` 存一篇摘要（非新建站点文章）。
    - scheduled_run=True：每日到点强制重新生成并推送（不因已发过而跳过）。
    - regenerate=True：强制按当日已发布内容重写摘要后再推送。
    - manual_run=True：跳过后台定时总开关检查（管理端手动触发）；可沿用库内稿仅推送。
    """
    own_session = db is None
    db = db or SessionLocal()
    try:
        if settings is None:
            settings = get_newsletter_settings_merged(db)
        if not settings.get("daily_digest_job_enabled", True) and not manual_run:
            return {"skipped": True, "reason": "daily_digest_job_disabled"}
        if not settings.get("cron_enabled", True) and not manual_run:
            return {"skipped": True, "reason": "cron_disabled"}

        if scheduled_run:
            regenerate = True

        d = date.fromisoformat(digest_date) if digest_date else shanghai_calendar_today()
        digest_key = d.isoformat()
        row = db.scalar(select(NewsletterDailyDigest).where(NewsletterDailyDigest.digest_date == digest_key))
        has_ready = _digest_has_content(row)

        if push_only and not has_ready:
            from .newsletter_period_digest import normalize_feishu_cadence, run_manual_feishu_period_push

            cadence_early = normalize_feishu_cadence(settings.get("feishu_push_cadence"))
            feishu_only_push = (
                manual_run
                and cadence_early != "daily"
                and bool(settings.get("feishu_enabled"))
                and bool((settings.get("feishu_webhook_url") or "").strip())
            )
            if feishu_only_push:
                period_out = run_manual_feishu_period_push(db, settings=settings)
                return {
                    "digest_date": digest_key,
                    "ok": bool(period_out.get("feishu_sent")),
                    "push_only": True,
                    **period_out,
                }
            return {
                "digest_date": digest_key,
                "ok": False,
                "error": "今日摘要尚未生成，请先「生成并推送」或等待定时任务。",
            }

        if (
            manual_run
            and not scheduled_run
            and not regenerate
            and not push_only
            and row
            and _digest_delivery_complete(row, settings)
        ):
            return {
                "skipped": True,
                "reason": "already_delivered",
                "digest_date": digest_key,
                "message": "今日摘要已生成且已推送，手动任务跳过（定时任务每日仍会重发）。",
            }

        apps_limit = int(settings.get("apps_limit") or 12)
        news_limit = int(settings.get("news_limit") or 12)
        apps, news = fetch_articles_for_shanghai_day_split(db, d, apps_limit=apps_limit, news_limit=news_limit)

        if regenerate:
            need_generate = True
        elif push_only or has_ready:
            need_generate = False
        else:
            need_generate = not row or not (row.body_md or "").strip() or row.status == "failed"

        content_generated = False
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
            content_generated = True
            db.expire_all()
            row = db.scalar(select(NewsletterDailyDigest).where(NewsletterDailyDigest.digest_date == digest_key))
        if not row or row.status != "ready" or not (row.body_md or "").strip():
            return {
                "digest_date": digest_key,
                "ok": False,
                "status": getattr(row, "status", "missing") if row else "missing",
                "error": getattr(row, "error_message", None) if row else "生成摘要失败或未开启「生成」",
            }

        if content_generated:
            apps_count, news_count = len(apps), len(news)
        else:
            apps_count, news_count = _article_counts_from_row(row)

        out: dict[str, Any] = {
            "digest_date": digest_key,
            "ok": True,
            "generated": content_generated,
            "reused_existing": has_ready and not content_generated,
            "apps_count": apps_count,
            "news_count": news_count,
            "email_sent": False,
            "feishu_sent": False,
        }
        if out["reused_existing"]:
            out["message"] = f"沿用库内今日摘要（{apps_count} 应用 / {news_count} 资讯），未重复生成。"
        elif content_generated:
            out["message"] = (
                f"已生成并落库今日摘要（{apps_count} 应用 / {news_count} 资讯，"
                f"美东 {digest_key} 当天已发布内容）。"
            )

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

        from .newsletter_period_digest import normalize_feishu_cadence, run_manual_feishu_period_push

        feishu_cadence = normalize_feishu_cadence(settings.get("feishu_push_cadence"))
        feishu_on = bool(settings.get("feishu_enabled")) and bool((settings.get("feishu_webhook_url") or "").strip())
        if feishu_on and feishu_cadence != "daily":
            period_out = run_manual_feishu_period_push(db, settings=settings) if manual_run else {}
            if manual_run:
                if period_out.get("feishu_sent"):
                    out["feishu_sent"] = True
                    out["feishu_period"] = period_out
                    prev_msg = str(out.get("message") or "")
                    out["message"] = f"{prev_msg} {period_out.get('message', '')}".strip()
                elif period_out.get("error"):
                    return {**out, "ok": False, "error": period_out.get("error")}
                elif not period_out.get("skipped"):
                    out["feishu_period"] = period_out
        if feishu_on and feishu_cadence == "daily":
            db.expire_all()
            row = db.scalar(select(NewsletterDailyDigest).where(NewsletterDailyDigest.digest_date == digest_key))
            already_feishu = bool(row and row.feishu_sent_at is not None)
            should_send_feishu = row and (
                row.feishu_sent_at is None or manual_run or scheduled_run
            )
            if should_send_feishu:
                if (manual_run or scheduled_run) and already_feishu:
                    row.feishu_sent_at = None
                    db.commit()
                try:
                    send_digest_to_feishu(
                        db,
                        digest_date=digest_key,
                        settings=settings,
                        apps_count=apps_count,
                        news_count=news_count,
                    )
                    out["feishu_sent"] = True
                    if manual_run and already_feishu:
                        out["feishu_resent"] = True
                    logger.info(
                        "newsletter daily feishu sent digest_date=%s apps=%s news=%s manual=%s",
                        digest_key,
                        apps_count,
                        news_count,
                        manual_run,
                    )
                except Exception as e:
                    logger.exception("newsletter daily feishu send failed: %s", e)
                    r2 = db.scalar(select(NewsletterDailyDigest).where(NewsletterDailyDigest.digest_date == digest_key))
                    if r2:
                        prev = (r2.error_message or "").strip()
                        r2.error_message = f"{prev}; feishu: {e}"[:2000].strip("; ")
                        db.commit()
                    return {**out, "ok": False, "error": str(e)}
            elif already_feishu:
                out["feishu_sent"] = True
                out["feishu_skipped"] = "already_sent"
            elif not row or not (row.body_md or "").strip():
                return {**out, "ok": False, "error": "今日摘要无正文，无法推送飞书"}
        elif settings.get("feishu_enabled", False):
            out["feishu_skip"] = "no_webhook"

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
