"""Pytest 全局：E2E 跳过 API 签名校验（需在导入 `backend.app.main` 之前设置）。"""
import os

os.environ.setdefault("AISOU_SKIP_API_SIGNATURE", "1")
