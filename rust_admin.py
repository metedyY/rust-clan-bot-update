from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import random
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import aiohttp
import discord
from discord import app_commands

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
IP_BANS_FILE = DATA_DIR / "ip_bans.json"
PLAYER_CACHE_FILE = DATA_DIR / "player_ip_cache.json"

RCON_HOST = os.getenv("RUST_RCON_HOST", "").strip()
RCON_PORT = os.getenv("RUST_RCON_PORT", "28016").strip()
RCON_PASSWORD = os.getenv("RUST_RCON_PASSWORD", "").strip()
RCON_SCHEME = os.getenv("RUST_RCON_SCHEME", "ws").strip().lower() or "ws"
IP_MONITOR_SECONDS = max(5, int(os.getenv("RUST_IP_BAN_CHECK_SECONDS", "15") or "15"))

BAN_ROLE_NAMES = {"👑 Clan Owner", "🛠️ Moderator"}
STEAM64_RE = re.compile(r"^\d{17}$")

_state_lock = asyncio.Lock()


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_json(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _save_json(path: Path, data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _rcon_ready() -> bool:
    if not RCON_HOST or not RCON_PASSWORD:
        return False
    try:
        return 1 <= int(RCON_PORT) <= 65535
    except ValueError:
        return False


def _rcon_url() -> str:
    if RCON_SCHEME not in {"ws", "wss"}:
        raise RuntimeError("RUST_RCON_SCHEME yalnızca ws veya wss olabilir.")
    try:
        port = int(RCON_PORT)
    except ValueError as exc:
        raise RuntimeError("RUST_RCON_PORT geçerli bir port değil.") from exc
    if not 1 <= port <= 65535:
        raise RuntimeError("RUST_RCON_PORT 1-65535 arasında olmalı.")

    host = RCON_HOST
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    password = quote(RCON_PASSWORD, safe="")
    return f"{RCON_SCHEME}://{host}:{port}/{password}"


def _safe_console_text(value: str, *, max_length: int = 180) -> str:
    value = value.replace("\r", " ").replace("\n", " ")
    value = value.replace(";", ",").replace('"', "'").replace("\\", "/")
    value = " ".join(value.split())
    return value[:max_length] or "Discord ban"


def _extract_ip(address: object) -> str | None:
    if not isinstance(address, str):
        return None
    value = address.strip()
    if not value:
        return None

    if value.startswith("[") and "]" in value:
        candidate = value[1:value.index("]")]
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            return None

    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        pass

    host, sep, port = value.rpartition(":")
    if sep and port.isdigit() and host:
        try:
            return str(ipaddress.ip_address(host))
        except ValueError:
            return None
    return None


async def _rcon_request(command: str, *, timeout: float = 12.0) -> str:
    if not _rcon_ready():
        raise RuntimeError(
            "Rust RCON ayarlanmamış. .env içine RUST_RCON_HOST, RUST_RCON_PORT ve "
            "RUST_RCON_PASSWORD eklenmeli."
        )

    identifier = random.randint(1001, 2_000_000_000)
    packet = {
        "Identifier": identifier,
        "Message": command,
        "Name": "WebRcon",
    }
    client_timeout = aiohttp.ClientTimeout(total=timeout)

    try:
        async with aiohttp.ClientSession(timeout=client_timeout) as session:
            async with session.ws_connect(_rcon_url(), heartbeat=20) as ws:
                await ws.send_json(packet)
                while True:
                    message = await ws.receive()
                    if message.type == aiohttp.WSMsgType.TEXT:
                        try:
                            payload = json.loads(message.data)
                        except (ValueError, TypeError):
                            continue
                        if payload.get("Identifier") == identifier:
                            return str(payload.get("Message", ""))
                    elif message.type in {
                        aiohttp.WSMsgType.CLOSE,
                        aiohttp.WSMsgType.CLOSED,
                        aiohttp.WSMsgType.ERROR,
                    }:
                        raise RuntimeError("Rust RCON bağlantısı yanıt gelmeden kapandı.")
    except asyncio.TimeoutError as exc:
        raise RuntimeError("Rust RCON zaman aşımına uğradı.") from exc
    except aiohttp.ClientError as exc:
        raise RuntimeError(f"Rust RCON bağlantı hatası: {exc}") from exc


async def _get_players() -> list[dict]:
    response = await _rcon_request("playerlist")
    try:
        raw = json.loads(response)
    except (ValueError, TypeError) as exc:
        raise RuntimeError("Rust playerlist yanıtı JSON olarak okunamadı.") from exc
    if not isinstance(raw, list):
        raise RuntimeError("Rust playerlist beklenmeyen veri döndürdü.")
    return [item for item in raw if isinstance(item, dict)]


def _player_steam_id(player: dict) -> str:
    value = player.get("SteamID", player.get("steamid", ""))
    return str(value).strip()


def _player_name(player: dict) -> str:
    value = player.get("DisplayName", player.get("displayName", "Oyuncu"))
    return str(value).strip() or "Oyuncu"


def _player_ip(player: dict) -> str | None:
    return _extract_ip(player.get("Address", player.get("address")))


async def _refresh_player_cache(players: list[dict]) -> dict:
    async with _state_lock:
        cache = _load_json(PLAYER_CACHE_FILE)
        for player in players:
            steam_id = _player_steam_id(player)
            ip = _player_ip(player)
            if not steam_id or ip is None:
                continue
            cache[steam_id] = {
                "ip": ip,
                "name": _player_name(player),
                "last_seen": _utcnow_iso(),
            }
        _save_json(PLAYER_CACHE_FILE, cache)
        return cache


async def _find_player_context(steam_id: str) -> tuple[str, str | None, bool]:
    players = await _get_players()
    cache = await _refresh_player_cache(players)

    for player in players:
        if _player_steam_id(player) == steam_id:
            return _player_name(player), _player_ip(player), True

    cached = cache.get(steam_id, {})
    if isinstance(cached, dict):
        return str(cached.get("name") or "Oyuncu"), _extract_ip(cached.get("ip")), False
    return "Oyuncu", None, False


async def _add_ip_ban(ip: str, steam_id: str, name: str, reason: str) -> None:
    async with _state_lock:
        bans = _load_json(IP_BANS_FILE)
        current = bans.get(ip)
        if not isinstance(current, dict):
            current = {}
        blocked = current.get("blocked_steam_ids", [])
        if not isinstance(blocked, list):
            blocked = []
        blocked_ids = {str(item) for item in blocked}
        blocked_ids.add(steam_id)
        bans[ip] = {
            "source_steam_id": str(current.get("source_steam_id") or steam_id),
            "source_name": str(current.get("source_name") or name),
            "reason": str(current.get("reason") or reason),
            "created_at": str(current.get("created_at") or _utcnow_iso()),
            "blocked_steam_ids": sorted(blocked_ids),
        }
        _save_json(IP_BANS_FILE, bans)


async def _mark_ip_blocked(ip: str, steam_id: str) -> None:
    async with _state_lock:
        bans = _load_json(IP_BANS_FILE)
        current = bans.get(ip)
        if not isinstance(current, dict):
            return
        blocked = current.get("blocked_steam_ids", [])
        if not isinstance(blocked, list):
            blocked = []
        blocked_ids = {str(item) for item in blocked}
        blocked_ids.add(steam_id)
        current["blocked_steam_ids"] = sorted(blocked_ids)
        current["last_enforced_at"] = _utcnow_iso()
        bans[ip] = current
        _save_json(IP_BANS_FILE, bans)


def _can_ban(interaction: discord.Interaction) -> bool:
    member = interaction.user
    if not isinstance(member, discord.Member):
        return False
    if interaction.guild is not None and member.id == interaction.guild.owner_id:
        return True
    if member.guild_permissions.administrator:
        return True
    return any(role.name in BAN_ROLE_NAMES for role in member.roles)


async def _enforce_ip_bans_once() -> None:
    if not _rcon_ready():
        return

    players = await _get_players()
    await _refresh_player_cache(players)

    async with _state_lock:
        bans = _load_json(IP_BANS_FILE)

    if not bans:
        return

    for player in players:
        steam_id = _player_steam_id(player)
        ip = _player_ip(player)
        if not steam_id or ip is None:
            continue
        record = bans.get(ip)
        if not isinstance(record, dict):
            continue
        blocked = record.get("blocked_steam_ids", [])
        blocked_ids = {str(item) for item in blocked} if isinstance(blocked, list) else set()
        if steam_id in blocked_ids:
            continue

        player_name = _safe_console_text(_player_name(player), max_length=80)
        source_id = str(record.get("source_steam_id") or "bilinmiyor")
        reason = _safe_console_text(
            f"Kalıcı IP ban eşleşmesi (kaynak SteamID: {source_id})",
            max_length=160,
        )
        try:
            await _rcon_request(f'banid {steam_id} "{player_name}" "{reason}"')
            await _rcon_request(f'kick {steam_id} "{reason}"')
            await _rcon_request("server.writecfg")
            await _mark_ip_blocked(ip, steam_id)
        except RuntimeError:
            continue


async def _ip_ban_monitor() -> None:
    while True:
        try:
            await _enforce_ip_bans_once()
        except Exception:
            pass
        await asyncio.sleep(IP_MONITOR_SECONDS)


def register_rust_admin(bot: discord.Client) -> None:
    if getattr(bot, "_arctic_rust_admin_registered", False):
        return
    setattr(bot, "_arctic_rust_admin_registered", True)

    ban_group = app_commands.Group(
        name="ban",
        description="Rust sunucusu ban yönetimi.",
    )

    @ban_group.command(name="perma", description="Steam64ID ile kalıcı Rust + IP ban uygular.")
    @app_commands.guild_only()
    @app_commands.describe(
        oyuncu_id="Banlanacak oyuncunun 17 haneli Steam64ID değeri",
        sebep="Ban sebebi",
    )
    async def ban_perma(
        interaction: discord.Interaction,
        oyuncu_id: str,
        sebep: str = "Kalıcı ban",
    ) -> None:
        if not _can_ban(interaction):
            await interaction.response.send_message(
                "Bu komutu yalnızca **Clan Owner**, **Moderator** veya sunucu yöneticisi kullanabilir.",
                ephemeral=True,
            )
            return

        steam_id = oyuncu_id.strip()
        if not STEAM64_RE.fullmatch(steam_id):
            await interaction.response.send_message(
                "Oyuncu ID, **17 haneli Steam64ID** olmalı.",
                ephemeral=True,
            )
            return

        if not _rcon_ready():
            await interaction.response.send_message(
                "Rust RCON henüz ayarlı değil. `.env` içine `RUST_RCON_HOST`, "
                "`RUST_RCON_PORT` ve `RUST_RCON_PASSWORD` eklenmeli.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        reason = _safe_console_text(sebep, max_length=160)

        try:
            name, ip, online = await _find_player_context(steam_id)
            safe_name = _safe_console_text(name, max_length=80)

            await _rcon_request(f'banid {steam_id} "{safe_name}" "{reason}"')
            if online:
                await _rcon_request(f'kick {steam_id} "{reason}"')
            await _rcon_request("server.writecfg")

            if ip is not None:
                await _add_ip_ban(ip, steam_id, name, reason)
        except RuntimeError as exc:
            await interaction.followup.send(f"Ban uygulanamadı: `{exc}`", ephemeral=True)
            return

        if ip is None:
            await interaction.followup.send(
                f"✅ `{steam_id}` Rust sunucusunda **kalıcı SteamID ban** aldı.\n"
                "⚠️ Oyuncunun IP'si mevcut `playerlist`/önbellekte bulunamadığı için IP koruması eklenemedi. "
                "Oyuncu bot bu sistemi izlerken en az bir kez sunucuda görünmüş olmalı.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"✅ `{steam_id}` için **kalıcı ban** uygulandı.\n"
            f"🌐 IP: `{ip}` kalıcı IP-ban listesine eklendi. Aynı IP ile gelen yeni Steam hesapları "
            f"en geç yaklaşık **{IP_MONITOR_SECONDS} saniye** içinde otomatik banlanıp atılır.",
            ephemeral=True,
        )

    bot.tree.add_command(ban_group)

    async def _rust_admin_ready() -> None:
        task = getattr(bot, "_arctic_ip_ban_task", None)
        if task is None or task.done():
            setattr(bot, "_arctic_ip_ban_task", asyncio.create_task(_ip_ban_monitor()))

    bot.add_listener(_rust_admin_ready, "on_ready")
