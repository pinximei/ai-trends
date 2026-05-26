"""首页雷达：源数量与合并顺序。"""
from backend.app.services import ACTIVE_ADMIN_SOURCE_KEYS
from backend.app.application.home_public import HOME_MAIN_SOURCE_KEYS


def test_home_main_keys_match_active_admin_sources() -> None:
    assert HOME_MAIN_SOURCE_KEYS == ACTIVE_ADMIN_SOURCE_KEYS
    assert len(HOME_MAIN_SOURCE_KEYS) == 6
