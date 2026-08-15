from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
BACKUPS_DIR = BASE_DIR / "backups"
PATCH_FILE = BASE_DIR / "patches.json"


def newest_backup() -> Path:
    if not BACKUPS_DIR.is_dir():
        raise RuntimeError("Güncelleme yedeği bulunamadı.")
    candidates = [p for p in BACKUPS_DIR.iterdir() if p.is_dir() and p.name.startswith("update_")]
    if not candidates:
        raise RuntimeError("Güncelleme yedeği bulunamadı.")
    return max(candidates, key=lambda p: p.stat().st_mtime)


def restore_backup(source: Path) -> None:
    ignored = {".env", "backups", "__pycache__", ".git", ".venv", "venv"}
    for item in source.iterdir():
        if item.name in ignored:
            continue
        target = BASE_DIR / item.name
        if item.is_dir():
            if target.exists() and target.is_file():
                target.unlink()
            shutil.copytree(item, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", ".env"))
        else:
            shutil.copy2(item, target)


def apply_patches(config: dict) -> None:
    for patch in config.get("replacements", []):
        rel = patch.get("file", "")
        old = patch.get("old", "")
        new = patch.get("new", "")
        if not rel or not old:
            continue
        target = (BASE_DIR / rel).resolve()
        target.relative_to(BASE_DIR.resolve())
        if not target.is_file():
            continue
        text = target.read_text(encoding="utf-8")
        if old in text:
            target.write_text(text.replace(old, new), encoding="utf-8")


def main() -> None:
    config = json.loads(PATCH_FILE.read_text(encoding="utf-8")) if PATCH_FILE.is_file() else {}
    backup = newest_backup()
    restore_backup(backup)
    apply_patches(config)

    try:
        PATCH_FILE.unlink(missing_ok=True)
    except OSError:
        pass

    real_bot = BASE_DIR / "bot.py"
    os.execv(sys.executable, [sys.executable, str(real_bot)])


if __name__ == "__main__":
    main()
