"""数据源「所属领域/板块」：支持多条，存 JSON 文本列。"""
from __future__ import annotations

import json

from .models import AdminSourceConfig


def parse_scope_labels_json(raw: str | None) -> list[str]:
    if not raw or raw == "[]":
        return []
    try:
        v = json.loads(raw)
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
    except Exception:
        pass
    return []


def dump_scope_labels_json(labels: list[str]) -> str:
    clean = [x.strip() for x in labels if x and str(x).strip()]
    return json.dumps(clean, ensure_ascii=False)


def get_scope_labels_from_source(item: AdminSourceConfig) -> list[str]:
    """读取数据源的全部领域标签；兼容仅有旧字段 scope_label 的行。"""
    raw = getattr(item, "scope_labels_json", None)
    if isinstance(raw, str) and raw.strip() and raw.strip() != "[]":
        got = parse_scope_labels_json(raw)
        if got:
            return got
    s = (item.scope_label or "").strip()
    return [s] if s else []


def normalize_scope_labels_from_payload(payload: dict) -> list[str]:
    """从 POST body 得到去重后的标签列表。支持 scope_labels 数组或旧字段 scope_label。"""
    raw = payload.get("scope_labels")
    if isinstance(raw, list):
        out: list[str] = []
        for x in raw:
            t = str(x).strip()
            if t and t not in out:
                out.append(t)
        return out
    legacy = (payload.get("scope_label") or "").strip()
    return [legacy] if legacy else []


def apply_scope_labels_to_row(item: AdminSourceConfig, labels: list[str]) -> None:
    """写入 ORM 行：JSON 列 + 兼容旧列 scope_label（取第一条，截断长度）。"""
    item.scope_labels_json = dump_scope_labels_json(labels)
    item.scope_label = (labels[0][:128] if labels else "") or ""
