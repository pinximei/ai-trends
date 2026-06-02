"""飞书推送周期：按日（沿用日报落库）/ 按周 / 按月（按时间窗聚合后直推）。"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from ..newsletter_digest_format import (
    build_digest_body_from_articles,
    build_digest_subject_default,
    digest_delivery_texts,
    format_digest_for_delivery,
)
from ..newsletter_settings_service import get_newsletter_settings_merged, set_feishu_last_sent_period
from ..us_content_calendar import us_calendar_today
from .newsletter_daily_digest import (
    _build_llm_subject_payload,
    _parse_subject_json,
    fetch_articles_for_us_date_range_split,
)

logger = logging.getLogger(__name__)

FEISHU_CADENCES = frozenset({"daily", "weekly", "monthly"})


def normalize_feishu_cadence(raw: str | None) -> str:
    c = (raw or "daily").strip().lower()
    return c if c in FEISHU_CADENCES else "daily"


def _format_range_label(start: date, end: date) -> str:
    if start == end:
        return start.isoformat()
    if start.year == end.year and start.month == end.month:
        return f"{start.month}/{start.day}–{end.month}/{end.day}"
    return f"{start.isoformat()} – {end.isoformat()}"


def period_limits_for_cadence(settings: dict[str, Any], cadence: str) -> tuple[int, int]:
    apps = int(settings.get("apps_limit") or 12)
    news = int(settings.get("news_limit") or 12)
    if cadence == "weekly":
        return min(40, apps * 2), min(40, news * 2)
    if cadence == "monthly":
        return min(40, apps * 3), min(40, news * 3)
    return apps, news


def scheduled_period_window(cadence: str, today: date, *, weekly_weekday: int) -> tuple[date, date, str] | None:
    """
    定时任务用的周期窗口与 period_key。
    返回 None 表示今日不应触发该周期的定时飞书推送。
    """
    cadence = normalize_feishu_cadence(cadence)
    if cadence == "daily":
        return today, today, today.isoformat()

    if cadence == "weekly":
        wd = max(0, min(6, int(weekly_weekday)))
        if today.weekday() != wd:
            return None
        this_monday = today - timedelta(days=today.weekday())
        prev_monday = this_monday - timedelta(days=7)
        prev_sunday = this_monday - timedelta(days=1)
        iso = prev_monday.isocalendar()
        return prev_monday, prev_sunday, f"{iso.year}-W{iso.week:02d}"

    if cadence == "monthly":
        if today.day != 1:
            return None
        last_day_prev = today.replace(day=1) - timedelta(days=1)
        start = last_day_prev.replace(day=1)
        key = f"{last_day_prev.year}-{last_day_prev.month:02d}"
        return start, last_day_prev, key

    return None


def manual_period_window(cadence: str, today: date) -> tuple[date, date, str]:
    """管理端「立即推送」：周报=近 7 日；月报=本月 1 日至今日。"""
    cadence = normalize_feishu_cadence(cadence)
    if cadence == "weekly":
        end = today
        start = today - timedelta(days=6)
        iso = start.isocalendar()
        return start, end, f"manual-W{iso.year}-{iso.week:02d}-{end.isoformat()}"
    if cadence == "monthly":
        start = today.replace(day=1)
        return start, today, f"manual-M{today.year}-{today.month:02d}-{today.isoformat()}"
    return today, today, today.isoformat()


def should_skip_period_feishu(*, period_key: str, last_sent: str, manual_run: bool) -> bool:
    if manual_run:
        return False
    return bool(last_sent) and last_sent == period_key


def _build_period_digest_text(
    db: Session,
    *,
    start: date,
    end: date,
    period_key: str,
    cadence: str,
    settings: dict[str, Any],
) -> tuple[str, str, list[Any], list[Any]]:
    apps_lim, news_lim = period_limits_for_cadence(settings, cadence)
    apps, news = fetch_articles_for_us_date_range_split(
        db, start, end, apps_limit=apps_lim, news_limit=news_lim
    )
    range_label = _format_range_label(start, end)
    digest_date = period_key
    public_base = str(settings.get("public_site_base_url") or "").strip()
    hl_apps = max(0, min(8, int(settings.get("llm_apps_limit", 3))))
    hl_news = max(0, min(8, int(settings.get("llm_news_limit", 3))))
    from ..application.article_public import _monetization_counts_as_apps_feed

    mon_apps = [a for a in apps if _monetization_counts_as_apps_feed(a)]
    reg_apps = [a for a in apps if a not in mon_apps]
    body_md = build_digest_body_from_articles(
        apps,
        news,
        highlight_apps=hl_apps,
        highlight_news=hl_news,
        monetization_apps=mon_apps,
        regular_apps=reg_apps,
    )
    period_suffix = {"weekly": "周报", "monthly": "月报"}.get(cadence, "")
    subject = build_digest_subject_default(
        digest_date,
        apps,
        news,
        period_label=range_label,
        period_kind=period_suffix or None,
    )

    llm_apps = max(0, min(8, int(settings.get("llm_apps_limit", 3))))
    llm_news = max(0, min(8, int(settings.get("llm_news_limit", 3))))
    from ..llm_service import chat_completion
    from ..llm_settings_service import resolve_llm_http_config
    from ..newsletter_digest_format import DIGEST_SUBJECT_LLM_SYSTEM

    _base, llm_key, _model = resolve_llm_http_config(db)
    if (llm_apps or llm_news) and llm_key:
        user = _build_llm_subject_payload(apps[:llm_apps], news[:llm_news], f"{range_label} ({period_suffix or '精选'})")
        raw, _it, _ot, _ = chat_completion(
            db,
            system=DIGEST_SUBJECT_LLM_SYSTEM,
            user=user,
            scenario="newsletter_period_digest",
            ref_type="newsletter_period_digest",
            ref_id=period_key,
            response_json=True,
            max_tokens=128,
        )
        subj_llm = _parse_subject_json(raw)
        if subj_llm:
            subject = subj_llm

    body_md, _email_plain, _feishu = format_digest_for_delivery(
        body_md,
        subject,
        digest_date=range_label,
        public_site_base_url=public_base,
        apps=apps,
        news=news,
    )
    return subject, body_md, apps, news


def send_feishu_period_digest(
    db: Session,
    *,
    settings: dict[str, Any],
    start: date,
    end: date,
    period_key: str,
    cadence: str,
    manual_run: bool = False,
) -> dict[str, Any]:
    from ..newsletter_feishu import send_daily_digest_feishu

    cadence = normalize_feishu_cadence(cadence)
    if not settings.get("feishu_enabled"):
        return {"skipped": True, "reason": "feishu_disabled"}
    webhook = str(settings.get("feishu_webhook_url") or "").strip()
    if not webhook:
        return {"skipped": True, "reason": "no_webhook", "feishu_skip": "no_webhook"}

    last_sent = str(settings.get("feishu_last_sent_period") or "").strip()
    if should_skip_period_feishu(period_key=period_key, last_sent=last_sent, manual_run=manual_run):
        return {
            "skipped": True,
            "reason": "period_already_sent",
            "period_key": period_key,
            "message": f"本周期（{period_key}）飞书已推送，定时任务跳过。",
        }

    subject, body_md, apps, news = _build_period_digest_text(
        db,
        start=start,
        end=end,
        period_key=period_key,
        cadence=cadence,
        settings=settings,
    )
    if not (body_md or "").strip():
        return {"ok": False, "error": "周期内无正文可推送", "period_key": period_key}

    range_label = _format_range_label(start, end)
    public_base = str(settings.get("public_site_base_url") or "").strip()
    _, feishu_text = digest_delivery_texts(
        body_md,
        subject,
        digest_date=range_label,
        public_site_base_url=public_base,
        apps_count=len(apps),
        news_count=len(news),
        period_kind=cadence,
    )
    send_daily_digest_feishu(webhook_url=webhook, text=feishu_text)
    set_feishu_last_sent_period(db, period_key)
    logger.info(
        "newsletter feishu %s sent period_key=%s range=%s..%s apps=%s news=%s manual=%s",
        cadence,
        period_key,
        start,
        end,
        len(apps),
        len(news),
        manual_run,
    )
    return {
        "ok": True,
        "feishu_sent": True,
        "period_key": period_key,
        "cadence": cadence,
        "range_start": start.isoformat(),
        "range_end": end.isoformat(),
        "apps_count": len(apps),
        "news_count": len(news),
        "message": f"已推送飞书{cadence}报（{range_label}，{len(apps)} 应用 / {len(news)} 资讯）。",
    }


def run_scheduled_feishu_period_push(db: Session, *, settings: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = settings or get_newsletter_settings_merged(db)
    cadence = normalize_feishu_cadence(settings.get("feishu_push_cadence"))
    if cadence == "daily":
        return {"skipped": True, "reason": "daily_uses_digest_row"}
    today = us_calendar_today()
    weekly_wd = int(settings.get("feishu_weekly_weekday", 0))
    window = scheduled_period_window(cadence, today, weekly_weekday=weekly_wd)
    if window is None:
        return {"skipped": True, "reason": "not_scheduled_day", "cadence": cadence}
    start, end, period_key = window
    return send_feishu_period_digest(
        db,
        settings=settings,
        start=start,
        end=end,
        period_key=period_key,
        cadence=cadence,
        manual_run=False,
    )


def run_manual_feishu_period_push(db: Session, *, settings: dict[str, Any]) -> dict[str, Any]:
    cadence = normalize_feishu_cadence(settings.get("feishu_push_cadence"))
    if cadence == "daily":
        return {"skipped": True, "reason": "daily_uses_digest_row"}
    today = us_calendar_today()
    start, end, period_key = manual_period_window(cadence, today)
    return send_feishu_period_digest(
        db,
        settings=settings,
        start=start,
        end=end,
        period_key=period_key,
        cadence=cadence,
        manual_run=True,
    )
