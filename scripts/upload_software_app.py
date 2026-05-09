#!/usr/bin/env python3
"""
将安装包写入本库 product_software_downloads + data/software_uploads（与后台上传等价）。

用法（在仓库根目录，已 pip install -e .）:
  py -3.12 scripts/upload_software_app.py --file ./app.apk --title "演示包" --platform android \\
    --category-slug tools --category-label 工具链

可选: AITRENDS_DATABASE_URL=sqlite:///... 指向与线上一致的数据库。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    p = argparse.ArgumentParser(description="CLI 上传应用安装包")
    p.add_argument("--file", required=True, help="本地文件路径")
    p.add_argument("--title", required=True)
    p.add_argument("--summary", default="")
    p.add_argument("--platform", required=True, choices=("ios", "android"))
    p.add_argument("--category-slug", default="general")
    p.add_argument("--category-label", default="")
    p.add_argument("--sort-order", type=int, default=0)
    p.add_argument("--store-url", default="", help="可选外链（与本地包并存）")
    args = p.parse_args()

    fp = Path(args.file).expanduser().resolve()
    if not fp.is_file():
        print(f"file not found: {fp}", file=sys.stderr)
        return 2

    body = fp.read_bytes()
    if os.environ.get("AITRENDS_DATABASE_URL"):
        pass  # 已在子进程前由调用方设置

    from backend.app.db import SessionLocal
    from backend.app.software_package_service import create_software_package_with_file

    db = SessionLocal()
    try:
        row = create_software_package_with_file(
            db,
            title=args.title,
            summary=args.summary,
            platform=args.platform,
            category_slug=args.category_slug,
            category_label=args.category_label or args.category_slug,
            file_body=body,
            original_filename=fp.name,
            content_type=None,
            sort_order=args.sort_order,
            store_url=args.store_url or None,
            status="published",
        )
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1
    finally:
        db.close()

    print(f"ok id={row.id} title={row.title!r} download=/api/public/v1/software/downloads/{row.id}/file")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
