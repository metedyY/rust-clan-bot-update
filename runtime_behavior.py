from __future__ import annotations

import re
from pathlib import Path

EARLY_START = "# ARCTIC_EARLY_LOG_SILENCE_START"
EARLY_END = "# ARCTIC_EARLY_LOG_SILENCE_END"
START_MARKER = "# ARCTIC_QUIET_CONSOLE_START"
END_MARKER = "# ARCTIC_QUIET_CONSOLE_END"


def _remove_marked_block(text: str, start: str, end: str) -> str:
    pattern = re.compile(
        rf"\n?{re.escape(start)}.*?{re.escape(end)}\n?",
        flags=re.S,
    )
    return pattern.sub("\n", text)


def _remove_startup_role_layout(text: str) -> str:
    # Normal açılışta kullanıcının Discord'da elle yaptığı rol/izin ayarlarına dokunma.
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


def _inject_early_log_silence(text: str) -> str:
    block = '''# ARCTIC_EARLY_LOG_SILENCE_START
import logging as _arctic_early_logging
_arctic_early_logging.disable(_arctic_early_logging.CRITICAL)
# ARCTIC_EARLY_LOG_SILENCE_END

'''

    future = "from __future__ import annotations"
    if future in text:
        pos = text.find(future) + len(future)
        return text[:pos] + "\n\n" + block + text[pos:].lstrip("\r\n")
    return block + text


def _inject_quiet_console(text: str) -> str:
    block = r'''
# ARCTIC_QUIET_CONSOLE_START
# Başarılı açılışlarda CMD yalnızca tek durum satırı gösterir.
from pathlib import Path as _ArcticPath
from member_log import register_member_log as _arctic_register_member_log

_arctic_status_printed = False

# BİLGİ/gelen-giden sistemi mevcut bot eventlerini ezmeden ayrı listenerlarla çalışır.
_arctic_register_member_log(bot)


async def _arctic_status_listener():
    global _arctic_status_printed

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
        print("Güncellendi ve çalışıyor", flush=True)
    else:
        print("Açık çalışıyor", flush=True)


# Mevcut on_ready event'ini ezme; ayrı listener her durumda tetiklensin.
bot.add_listener(_arctic_status_listener, "on_ready")
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
    updated = _remove_marked_block(text, EARLY_START, EARLY_END)
    updated = _remove_marked_block(updated, START_MARKER, END_MARKER)
    updated = _remove_startup_role_layout(updated)
    updated = _inject_early_log_silence(updated)
    updated = _inject_quiet_console(updated)

    if updated != text:
        bot_path.write_text(updated, encoding="utf-8")
