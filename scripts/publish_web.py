"""Sync dashboard/dist and web/fallback to the web bucket (used by deploy)."""

from __future__ import annotations

import mimetypes
from pathlib import Path

from lantern_core import store
from lantern_core.config import ROOT_DIR, settings


def _upload_tree(root: Path, prefix: str = "") -> int:
    n = 0
    if not root.exists():
        return 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        key = f"{prefix}{rel}" if prefix else rel
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        store.put_object(key, path.read_bytes(), bucket=settings.WEB_BUCKET, content_type=ctype)
        n += 1
    return n


def main() -> None:
    dist = ROOT_DIR / "dashboard" / "dist"
    fallback = ROOT_DIR / "web" / "fallback"
    n = _upload_tree(dist) + _upload_tree(fallback, prefix="fallback/")
    print(f"published {n} objects to {settings.WEB_BUCKET}")


if __name__ == "__main__":
    main()
