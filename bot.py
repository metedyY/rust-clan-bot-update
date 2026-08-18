from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from runtime_behavior import apply_runtime_migration

BASE_DIR = Path(__file__).resolve().parent
BACKUPS_DIR = BASE_DIR / "backups"
PATCH_FILE = BASE_DIR / "patches.json"
UPDATE_MARKER = BASE_DIR / ".arctic_updated"


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
        "wipe_monitor_v2.py", "role_layout.py", "ticket_form_v2.py",
        "runtime_behavior.py", "member_log.py", "voice_log.py", "discord_ban.py",
        "message_purge.py",
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


def apply_ticket_steam_migration() -> None:
    """Eski ticket_system.py kullanan kurulumları da geriye dönük olarak günceller."""
    target = BASE_DIR / "ticket_system.py"
    if not target.is_file():
        return

    text = target.read_text(encoding="utf-8")
    updated = text

    if "steam_profile = discord.ui.TextInput(" not in updated:
        old_fields = '''    activity = discord.ui.TextInput(
        label="Günlük aktiflik",
        placeholder="Örn: Günde 5-6 saat, wipe günü tam aktif",
        min_length=2,
        max_length=100,
    )
    about = discord.ui.TextInput(
        label="Neden klana katılmak istiyorsun?",
        placeholder="Kısaca kendinden ve oyun tarzından bahset.",
        style=discord.TextStyle.paragraph,
        min_length=10,
        max_length=700,
    )'''
        new_fields = '''    steam_profile = discord.ui.TextInput(
        label="Steam profil linkin",
        placeholder="Örn: https://steamcommunity.com/id/kullaniciadi",
        min_length=20,
        max_length=200,
    )
    profile = discord.ui.TextInput(
        label="Aktiflik ve oyun tarzın",
        placeholder="Örn: Günde 5-6 saat aktifim. Roamer ağırlıklı oynuyorum.",
        style=discord.TextStyle.paragraph,
        min_length=10,
        max_length=700,
    )'''
        updated = updated.replace(old_fields, new_fields, 1)

    if "Geçerli bir Steam profil linki girmelisin" not in updated and "steam_profile = discord.ui.TextInput(" in updated:
        anchor = '''        await interaction.response.defer(ephemeral=True, thinking=True)

        try:'''
        steam_validation = '''        steam_url = str(self.steam_profile.value).strip()
        steam_pattern = r"^https?://(?:www\\.)?steamcommunity\\.com/(?:id|profiles)/[^/\\s?#]+/?(?:[?#].*)?$"
        if not re.match(steam_pattern, steam_url, flags=re.I):
            await interaction.response.send_message(
                "❌ Geçerli bir Steam profil linki girmelisin. Örnek: `https://steamcommunity.com/id/kullaniciadi`",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:'''
        updated = updated.replace(anchor, steam_validation, 1)

    old_embed = '''            embed.add_field(name="Ana Rol", value=str(self.main_role.value), inline=True)
            embed.add_field(name="Günlük Aktiflik", value=str(self.activity.value), inline=False)
            embed.add_field(name="Hakkında", value=str(self.about.value), inline=False)'''
    new_embed = '''            embed.add_field(name="Ana Rol", value=str(self.main_role.value), inline=True)
            embed.add_field(name="Steam Profili", value=f"<{steam_url}>", inline=False)
            embed.add_field(name="Aktiflik / Oyun Tarzı", value=str(self.profile.value), inline=False)'''
    updated = updated.replace(old_embed, new_embed, 1)

    old_panel = '''            "• Günlük aktiflik\\n"
            "• Kendin ve oyun tarzın hakkında kısa bilgi\\n\\n"'''
    new_panel = '''            "• Steam profil linki\\n"
            "  Örnek: `https://steamcommunity.com/id/kullaniciadi`\\n"
            "• Günlük aktiflik + kendin ve oyun tarzın hakkında kısa bilgi\\n\\n"'''
    updated = updated.replace(old_panel, new_panel, 1)

    if updated != text:
        target.write_text(updated, encoding="utf-8")


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
    # Başvuru butonu ve /basvuru-panel Steam alanlı v2 formunu kullanır.
    updated = updated.replace(
        "from ticket_system import (",
        "from ticket_form_v2 import (",
    )

    if updated != text:
        target.write_text(updated, encoding="utf-8")

    # Önceki yanlış Rust/RCON ban modülünü yerel kurulumdan kaldır.
    try:
        (BASE_DIR / "rust_admin.py").unlink(missing_ok=True)
    except OSError:
        pass

    # Normal açılışta rol/izin ayarlarına dokunma, ek listener/komutları bağla ve CMD çıktısını sadeleştir.
    apply_runtime_migration(target)


def main() -> None:
    config = json.loads(PATCH_FILE.read_text(encoding="utf-8")) if PATCH_FILE.is_file() else {}
    backup = newest_backup()
    restore_backup(backup)
    apply_patches(config)
    apply_ticket_steam_migration()
    apply_builtin_migrations()

    try:
        PATCH_FILE.unlink(missing_ok=True)
    except OSError:
        pass

    # Bir sonraki başarılı Discord bağlantısında "Güncellendi ve çalışıyor." yazdırılır.
    try:
        UPDATE_MARKER.write_text("1", encoding="utf-8")
    except OSError:
        pass

    real_bot = BASE_DIR / "bot.py"
    os.execv(sys.executable, [sys.executable, str(real_bot)])


if __name__ == "__main__":
    main()
