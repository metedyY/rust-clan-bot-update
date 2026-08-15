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
    # Paket içindeki yeni modüller korunur; yedekteki eski kopyalar üstüne yazılmaz.
    ignored = {
        ".env", "backups", "__pycache__", ".git", ".venv", "venv",
        "wipe_monitor_v2.py", "role_layout.py",
    }
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
        guard = patch.get("guard", "")
        if not rel or not old:
            continue
        target = (BASE_DIR / rel).resolve()
        target.relative_to(BASE_DIR.resolve())
        if not target.is_file():
            continue
        text = target.read_text(encoding="utf-8")
        if guard and guard in text:
            continue
        if old in text:
            target.write_text(text.replace(old, new), encoding="utf-8")


def apply_builtin_migrations() -> None:
    """Paket içindeki yeni modülleri gerçek bota bağlayan idempotent migrationlar."""
    target = BASE_DIR / "bot.py"
    if not target.is_file():
        return

    text = target.read_text(encoding="utf-8")
    updated = text.replace(
        "from wipe_monitor import register_wipe_system",
        "from wipe_monitor_v2 import register_wipe_system",
    )

    if "from role_layout import apply_arc_role_layout" not in updated:
        anchor = "from wipe_monitor_v2 import register_wipe_system"
        if anchor in updated:
            updated = updated.replace(
                anchor,
                anchor + "\nfrom role_layout import apply_arc_role_layout",
                1,
            )

    if "await apply_arc_role_layout(guild)" not in updated:
        presence_line = '    await bot.change_presence(activity=discord.Game(name="Rust Clan | Kurulum + Başvuru"))'
        if presence_line in updated:
            updated = updated.replace(
                presence_line,
                "    for guild in bot.guilds:\n"
                "        await apply_arc_role_layout(guild)\n"
                + presence_line,
                1,
            )

    if updated != text:
        target.write_text(updated, encoding="utf-8")


def main() -> None:
    config = json.loads(PATCH_FILE.read_text(encoding="utf-8")) if PATCH_FILE.is_file() else {}
    backup = newest_backup()
    restore_backup(backup)
    apply_patches(config)
    apply_builtin_migrations()

    try:
        PATCH_FILE.unlink(missing_ok=True)
    except OSError:
        pass

    real_bot = BASE_DIR / "bot.py"
    os.execv(sys.executable, [sys.executable, str(real_bot)])


if __name__ == "__main__":
    main()
