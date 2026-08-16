from __future__ import annotations

import re
from pathlib import Path

START_MARKER = "# ARCTIC_QUIET_CONSOLE_START"
END_MARKER = "# ARCTIC_QUIET_CONSOLE_END"


def _remove_old_console_block(text: str) -> str:
    pattern = re.compile(
        rf"\n?{re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}\n?",
        flags=re.S,
    )
    return pattern.sub("\n", text)


def _remove_startup_role_layout(text: str) -> str:
    # Kullanıcının Discord'da elle yaptığı rol ayarlarına normal açılışta dokunma.
    text = re.sub(
        r"^\s*from\s+role_layout\s+import\s+apply_arc_role_layout\s*$\n?",
        "",
        text,
        flags=re.M,
    )
    text = re.sub(
        r"\n[ \t]*for\s+guild\s+in\s+bot\.guilds\s*:\s*\r?\n"
        r"[ \t]+await\s+apply_arc_role_layout\(guild\)\s*\r?\n",
        "\n",
        text,
    )
    return text


def _inject_quiet_console(text: str) -> str:
    block = r'''
# ARCTIC_QUIET_CONSOLE_START
# Başarılı açılışlarda CMD yalnızca tek durum satırı gösterir.
import logging as _arctic_logging
from pathlib import Path as _ArcticPath

_arctic_logging.disable(_arctic_logging.CRITICAL)
_arctic_original_on_ready = getattr(bot, "on_ready", None)
_arctic_status_printed = False


async def _arctic_quiet_on_ready():
    global _arctic_status_printed

    if _arctic_original_on_ready is not None:
        await _arctic_original_on_ready()

    if _arctic_status_printed:
        return

    _arctic_status_printed = True
    _arctic_marker = _ArcticPath(__file__).resolve().parent / ".arctic_updated"
    _arctic_was_updated = _arctic_marker.exists()

    if _arctic_was_updated:
        try:
            _arctic_marker.unlink()
        except OSError:
            pass

    if _arctic_was_updated:
        print("Güncellendi ve çalışıyor.", flush=True)
    else:
        print("Açık, çalışıyor.", flush=True)


bot.on_ready = _arctic_quiet_on_ready
# ARCTIC_QUIET_CONSOLE_END

'''

    matches = list(re.finditer(r"(?m)^[ \t]*bot\.run\s*\(", text))
    if not matches:
        return text

    pos = matches[-1].start()
    return text[:pos] + block + text[pos:]


def apply_runtime_migration(bot_path: Path) -> None:
    """Gerçek bot.py üzerinde açılış davranışını güvenli ve idempotent şekilde düzenler."""
    if not bot_path.is_file():
        return

    text = bot_path.read_text(encoding="utf-8")
    updated = _remove_old_console_block(text)
    updated = _remove_startup_role_layout(updated)
    updated = _inject_quiet_console(updated)

    if updated != text:
        bot_path.write_text(updated, encoding="utf-8")
