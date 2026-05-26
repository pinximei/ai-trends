"""产品仅保留已验证可拉取的数据源。"""
from backend.app.services import (
    ACTIVE_ADMIN_SOURCE_KEYS,
    BUILTIN_ADMIN_SOURCE_KEYS,
    DISCONTINUED_BOOTSTRAP_ADMIN_SOURCES,
)


def test_active_sources_are_six_verified_keys() -> None:
    assert ACTIVE_ADMIN_SOURCE_KEYS == (
        "github",
        "product_hunt",
        "hacker_news",
        "newsapi",
        "thenewsapi",
        "acquire",
    )


def test_discontinued_not_in_builtin() -> None:
    assert not DISCONTINUED_BOOTSTRAP_ADMIN_SOURCES.intersection(BUILTIN_ADMIN_SOURCE_KEYS)
    assert "taaft" in DISCONTINUED_BOOTSTRAP_ADMIN_SOURCES
    assert "arxiv" in DISCONTINUED_BOOTSTRAP_ADMIN_SOURCES
