from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import socket
import struct
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger("rust-setup-bot.wipe")

BASE_DIR = Path(__file__).resolve().parent
STATE_DIR = BASE_DIR / "data"
STATE_PATH = STATE_DIR / "wipe_state.json"

WIPE_CHANNEL_ID_RAW = os.getenv("WIPE_CHANNEL_ID", "").strip()
WIPE_CHANNEL_NAME = os.getenv("WIPE_CHANNEL_NAME", "wipe-katilim").strip() or "wipe-katilim"
WIPE_MONITOR_ENABLED = os.getenv("WIPE_MONITOR_ENABLED", "true").strip().casefold() not in {
    "0", "false", "no", "off", "kapali", "kapalı"
}

try:
    _poll_seconds = int(os.getenv("WIPE_POLL_SECONDS", "90"))
except ValueError:
    _poll_seconds = 90
WIPE_POLL_SECONDS = min(900, max(30, _poll_seconds))

SURVIVORS_HOME = "https://survivors.gg/"
SURVIVORS_POLL_SECONDS = 300
HTTP_TIMEOUT_SECONDS = 10
SERVER_QUERY_TIMEOUT_SECONDS = 4.0
EVENT_RETENTION_DAYS = 45


@dataclass(frozen=True, slots=True)
class ServerSpec:
    key: str
    display_name: str
    network: str
    host: str
    game_port: int
    query_port: int
    source_url: str


MAIN_SERVERS: tuple[ServerSpec, ...] = (
    ServerSpec(
        "rustafied-us-main", "Rustafied US Main", "Rustafied",
        "usmain.rustafied.com", 28015, 28018, "https://www.rustafied.com/server",
    ),
    ServerSpec(
        "rustafied-eu-main", "Rustafied EU Main", "Rustafied",
        "eumain.rustafied.com", 28015, 28018, "https://www.rustafied.com/server",
    ),
    ServerSpec(
        "rustopia-us-main", "Rustopia US Main", "Rustopia",
        "usmain.rustopia.gg", 28015, 28010, "https://rustopia.gg/",
    ),
    ServerSpec(
        "rustopia-eu-main", "Rustopia EU Main", "Rustopia",
        "eumain.rustopia.gg", 28015, 28010, "https://rustopia.gg/",
    ),
    ServerSpec(
        "rustymoose-us-main", "Rusty Moose US Main", "Rusty Moose",
        "main.us-premium.moose.gg", 28010, 28015, "https://moose.gg/",
    ),
    ServerSpec(
        "rustymoose-eu-main", "Rusty Moose EU Main", "Rusty Moose",
        "main.eu.moose.gg", 28010, 28015, "https://moose.gg/",
    ),
    ServerSpec(
        "survivors-main", "Survivors.gg Main", "Survivors.gg",
        "main.survivors.gg", 28010, 28011, "https://survivors.gg/servers/",
    ),
)


@dataclass(slots=True)
class QueryInfo:
    name: str
    map_name: str
    keywords: str
    born: int | None
    players: int
    max_players: int


class _BufferReader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def read(self, count: int) -> bytes:
        end = self.pos + count
        if end > len(self.data):
            raise ValueError("A2S yanıtı beklenenden kısa.")
        out = self.data[self.pos:end]
        self.pos = end
        return out

    def u8(self) -> int:
        return self.read(1)[0]

    def u16(self) -> int:
        return struct.unpack("<H", self.read(2))[0]

    def u64(self) -> int:
        return struct.unpack("<Q", self.read(8))[0]

    def cstring(self) -> str:
        end = self.data.find(b"\x00", self.pos)
        if end == -1:
            raise ValueError("A2S metin alanı sonlandırılmamış.")
        raw = self.data[self.pos:end]
        self.pos = end + 1
        return raw.decode("utf-8", errors="replace")


def _parse_a2s_info(packet: bytes) -> QueryInfo:
    if not packet.startswith(b"\xff\xff\xff\xffI"):
        raise ValueError("Geçersiz A2S_INFO yanıtı.")

    r = _BufferReader(packet[5:])
    _protocol = r.u8()
    name = r.cstring()
    map_name = r.cstring()
    _folder = r.cstring()
    _game = r.cstring()
    _appid = r.u16()
    players = r.u8()
    max_players = r.u8()
    _bots = r.u8()
    _server_type = r.u8()
    _environment = r.u8()
    _visibility = r.u8()
    _vac = r.u8()
    _version = r.cstring()

    keywords = ""
    if r.pos < len(r.data):
        edf = r.u8()
        if edf & 0x80:
            r.u16()
        if edf & 0x10:
            r.u64()
        if edf & 0x40:
            r.u16()
            r.cstring()
        if edf & 0x20:
            keywords = r.cstring()
        if edf & 0x01:
            r.u64()

    match = re.search(r"(?:^|,)born(\d+)(?:,|$)", keywords)
    born = int(match.group(1)) if match else None
    return QueryInfo(
        name=name,
        map_name=map_name,
        keywords=keywords,
        born=born,
        players=players,
        max_players=max_players,
    )


def query_server(spec: ServerSpec) -> QueryInfo:
    address = (spec.host, spec.query_port)
    request = b"\xff\xff\xff\xffTSource Engine Query\x00"

    infos = socket.getaddrinfo(spec.host, spec.query_port, type=socket.SOCK_DGRAM)
    if not infos:
        raise OSError(f"DNS çözümlenemedi: {spec.host}")

    last_error: Exception | None = None
    for family, socktype, proto, _canonname, sockaddr in infos:
        try:
            with socket.socket(family, socktype, proto) as sock:
                sock.settimeout(SERVER_QUERY_TIMEOUT_SECONDS)
                sock.sendto(request, sockaddr)
                packet, _ = sock.recvfrom(65535)

                if packet.startswith(b"\xff\xff\xff\xffA") and len(packet) >= 9:
                    challenge = packet[5:9]
                    sock.sendto(request + challenge, sockaddr)
                    packet, _ = sock.recvfrom(65535)

                if packet.startswith(b"\xfe\xff\xff\xff"):
                    raise ValueError("Parçalı A2S_INFO yanıtı desteklenmiyor.")
                return _parse_a2s_info(packet)
        except (OSError, ValueError) as exc:
            last_error = exc

    if last_error:
        raise last_error
    raise OSError(f"Sunucu sorgulanamadı: {address}")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if text:
            self.parts.append(text)


def _download_text(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "ArcticRustBot/1.0 (+wipe-monitor)",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def _parse_survivors_today(html: str, now_utc: datetime) -> list[dict[str, Any]]:
    parser = _TextExtractor()
    parser.feed(html)
    text = " ".join(parser.parts)
    text = re.sub(r"\s+", " ", text)

    start_match = re.search(r"Today's\s+Wipes", text, flags=re.I)
    if not start_match:
        return []
    end_match = re.search(r"Next\s+Wipes", text[start_match.end():], flags=re.I)
    if end_match:
        section = text[start_match.end(): start_match.end() + end_match.start()]
    else:
        section = text[start_match.end(): start_match.end() + 2500]

    berlin = ZoneInfo("Europe/Berlin")
    local_now = now_utc.astimezone(berlin)

    pattern = re.compile(
        r"(Survivors\.gg(?:(?!Survivors\.gg|FULLWIPE|MAP\s+WIPE).){0,100}?)\s+"
        r"(FULLWIPE|MAP\s+WIPE)\s+(?:WIPED\s*[✓✔]?\s*)?"
        r"(\d{1,2}:\d{2})\s*(CEST|CET)",
        flags=re.I,
    )

    events: list[dict[str, Any]] = []
    for match in pattern.finditer(section):
        server_name = " ".join(match.group(1).split()).strip(" -|•")
        wipe_type = " ".join(match.group(2).upper().split())
        hour, minute = map(int, match.group(3).split(":"))

        if re.search(r"\bmain\b", server_name, flags=re.I):
            continue

        event_local = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        event_utc = event_local.astimezone(timezone.utc)
        events.append(
            {
                "server_name": server_name,
                "wipe_type": wipe_type,
                "event_time": event_utc,
                "fingerprint": (
                    f"survivors-site|{event_local.date().isoformat()}|"
                    f"{server_name.casefold()}|{wipe_type}|{hour:02d}:{minute:02d}"
                ),
            }
        )
    return events


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None = None) -> str:
    return (dt or _utc_now()).isoformat()


def _load_state() -> dict[str, Any]:
    try:
        raw = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            raw.setdefault("servers", {})
            raw.setdefault("events", {})
            return raw
    except (OSError, json.JSONDecodeError):
        pass
    return {"servers": {}, "events": {}}


def _write_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    temp = STATE_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(STATE_PATH)


def _channel_name_matches(name: str) -> bool:
    normalized = name.casefold().replace("ı", "i")
    choices = {
        WIPE_CHANNEL_NAME.casefold().replace("ı", "i"),
        "wipe-katilim",
        "wipe-katılım".casefold().replace("ı", "i"),
    }
    return normalized in choices


class WipeMonitor:
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.state = _load_state()
        self.state_lock = asyncio.Lock()
        self.task: asyncio.Task[None] | None = None
        self.last_survivors_poll: datetime | None = None
        self.health: dict[str, dict[str, Any]] = {
            spec.key: {"ok": None, "last_check": None, "last_error": None, "born": None}
            for spec in MAIN_SERVERS
        }
        self.site_health: dict[str, Any] = {"ok": None, "last_check": None, "last_error": None}

    def start(self) -> None:
        if not WIPE_MONITOR_ENABLED or (self.task and not self.task.done()):
            return
        self.task = asyncio.create_task(self.run(), name="arctic-wipe-monitor")

    async def run(self) -> None:
        await self.bot.wait_until_ready()
        log.info(
            "Wipe monitor aktif: %s Main sunucu, interval=%ss, kanal=%s",
            len(MAIN_SERVERS), WIPE_POLL_SECONDS, WIPE_CHANNEL_NAME,
        )
        while not self.bot.is_closed():
            started = _utc_now()
            await self.poll_main_servers()
            if (
                self.last_survivors_poll is None
                or (started - self.last_survivors_poll).total_seconds() >= SURVIVORS_POLL_SECONDS
            ):
                await self.poll_survivors_site()
                self.last_survivors_poll = started

            elapsed = (_utc_now() - started).total_seconds()
            await asyncio.sleep(max(5.0, WIPE_POLL_SECONDS - elapsed))

    async def poll_main_servers(self) -> None:
        results = await asyncio.gather(
            *(self._poll_one(spec) for spec in MAIN_SERVERS),
            return_exceptions=True,
        )
        for spec, result in zip(MAIN_SERVERS, results):
            if isinstance(result, BaseException):
                log.warning("Wipe source error [%s]: %s", spec.display_name, result)

    async def _poll_one(self, spec: ServerSpec) -> None:
        now = _utc_now()
        try:
            info = await asyncio.to_thread(query_server, spec)
        except Exception as exc:
            self.health[spec.key].update(
                ok=False,
                last_check=_iso(now),
                last_error=f"{type(exc).__name__}: {exc}",
            )
            return

        self.health[spec.key].update(
            ok=True,
            last_check=_iso(now),
            last_error=None,
            born=info.born,
            players=info.players,
            max_players=info.max_players,
            map=info.map_name,
        )

        if info.born is None:
            log.warning("%s A2S tags içinde born değeri bulunamadı.", spec.display_name)
            return

        async with self.state_lock:
            server_state = self.state["servers"].get(spec.key)
            if not isinstance(server_state, dict) or not server_state.get("born"):
                self.state["servers"][spec.key] = {
                    "born": info.born,
                    "server_name": info.name,
                    "map": info.map_name,
                    "observed_at": _iso(now),
                }
                _write_state(self.state)
                log.info("Wipe baseline [%s] born=%s", spec.display_name, info.born)
                return

            previous_born = int(server_state.get("born", 0))
            if info.born == previous_born:
                server_state.update(
                    server_name=info.name,
                    map=info.map_name,
                    observed_at=_iso(now),
                )
                return

            event_key = f"a2s|{spec.key}|{info.born}"
            already_seen = event_key in self.state["events"]
            born_dt = datetime.fromtimestamp(info.born, tz=timezone.utc)
            age = now - born_dt
            plausible = (
                info.born > previous_born
                and timedelta(minutes=-10) <= age <= timedelta(hours=12)
            )

            if already_seen or not plausible:
                server_state.update(
                    born=info.born,
                    server_name=info.name,
                    map=info.map_name,
                    observed_at=_iso(now),
                )
                _write_state(self.state)
                if not plausible:
                    log.warning(
                        "born değişti ama bildirim atlanıyor [%s]: %s -> %s (age=%s)",
                        spec.display_name, previous_born, info.born, age,
                    )
                return

        sent = await self.send_main_wipe(spec, info, born_dt)
        if not sent:
            return

        async with self.state_lock:
            server_state = self.state["servers"].setdefault(spec.key, {})
            server_state.update(
                born=info.born,
                server_name=info.name,
                map=info.map_name,
                observed_at=_iso(now),
            )
            self.state["events"][event_key] = _iso(now)
            self._prune_events_locked(now)
            _write_state(self.state)

    async def poll_survivors_site(self) -> None:
        now = _utc_now()
        try:
            html = await asyncio.to_thread(_download_text, SURVIVORS_HOME)
            events = _parse_survivors_today(html, now)
            self.site_health.update(ok=True, last_check=_iso(now), last_error=None, count=len(events))
        except Exception as exc:
            self.site_health.update(
                ok=False,
                last_check=_iso(now),
                last_error=f"{type(exc).__name__}: {exc}",
            )
            log.warning("Survivors.gg wipe page error: %s", exc)
            return

        for event in events:
            event_time: datetime = event["event_time"]
            age = now - event_time
            if not (timedelta(minutes=-3) <= age <= timedelta(hours=2)):
                continue

            async with self.state_lock:
                fingerprint = event["fingerprint"]
                if fingerprint in self.state["events"]:
                    continue

            sent = await self.send_survivors_wipe(event)
            if not sent:
                continue

            async with self.state_lock:
                self.state["events"][fingerprint] = _iso(now)
                self._prune_events_locked(now)
                _write_state(self.state)

    def _prune_events_locked(self, now: datetime) -> None:
        cutoff = now - timedelta(days=EVENT_RETENTION_DAYS)
        cleaned: dict[str, str] = {}
        for key, value in self.state.get("events", {}).items():
            try:
                stamp = datetime.fromisoformat(value)
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=timezone.utc)
                if stamp >= cutoff:
                    cleaned[key] = value
            except (TypeError, ValueError):
                continue
        self.state["events"] = cleaned

    def target_channels(self, guild: discord.Guild | None = None) -> list[discord.TextChannel]:
        channels: list[discord.TextChannel] = []
        raw_id = WIPE_CHANNEL_ID_RAW
        if raw_id:
            try:
                channel_id = int(raw_id)
            except ValueError:
                channel_id = 0
            channel = self.bot.get_channel(channel_id) if channel_id else None
            if isinstance(channel, discord.TextChannel):
                if guild is None or channel.guild.id == guild.id:
                    return [channel]

        guilds = [guild] if guild else list(self.bot.guilds)
        for item in guilds:
            if item is None:
                continue
            for channel in item.text_channels:
                if _channel_name_matches(channel.name):
                    channels.append(channel)
                    break
        return channels

    async def _send_embed(self, embed: discord.Embed, guild: discord.Guild | None = None) -> int:
        sent = 0
        for channel in self.target_channels(guild):
            try:
                await channel.send(
                    embed=embed,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                sent += 1
            except (discord.Forbidden, discord.HTTPException) as exc:
                log.warning("Wipe mesajı gönderilemedi [%s]: %s", channel, exc)
        if sent == 0:
            log.warning("Wipe hedef kanalı bulunamadı veya mesaj gönderilemedi: %s", WIPE_CHANNEL_NAME)
        return sent

    async def send_main_wipe(self, spec: ServerSpec, info: QueryInfo, born_dt: datetime) -> int:
        unix = int(born_dt.timestamp())
        embed = discord.Embed(
            title="RUST WIPE DUYURUSU",
            description=f"**{spec.display_name}** yeni bir wipe açtı.",
            colour=discord.Colour.from_rgb(105, 170, 220),
            timestamp=_utc_now(),
        )
        embed.add_field(name="Sunucu", value=spec.display_name, inline=True)
        embed.add_field(name="Durum", value="Yeni wipe algılandı", inline=True)
        embed.add_field(name="Wipe zamanı", value=f"<t:{unix}:F>\n<t:{unix}:R>", inline=False)
        embed.add_field(name="Harita", value=info.map_name or "Bilinmiyor", inline=True)
        embed.add_field(
            name="Bağlantı",
            value=f"`client.connect {spec.host}:{spec.game_port}`",
            inline=False,
        )
        embed.add_field(
            name="Doğrulama",
            value="Sunucunun canlı Rust query verisinde yeni dünya başlangıcı tespit edildi.",
            inline=False,
        )
        embed.set_footer(text="Arctic • Otomatik Wipe Takibi")
        return await self._send_embed(embed)

    async def send_survivors_wipe(self, event: dict[str, Any]) -> int:
        event_time: datetime = event["event_time"]
        unix = int(event_time.timestamp())
        label = "Full Wipe" if event["wipe_type"] == "FULLWIPE" else "Map Wipe"
        embed = discord.Embed(
            title="RUST WIPE DUYURUSU",
            description=f"**{event['server_name']}** için {label} zamanı geldi.",
            colour=discord.Colour.from_rgb(105, 170, 220),
            timestamp=_utc_now(),
        )
        embed.add_field(name="Sunucu", value=event["server_name"], inline=True)
        embed.add_field(name="Tür", value=label, inline=True)
        embed.add_field(name="Wipe zamanı", value=f"<t:{unix}:F>\n<t:{unix}:R>", inline=False)
        embed.add_field(name="Kaynak", value="Survivors.gg resmi wipe sayfası", inline=False)
        embed.set_footer(text="Arctic • Otomatik Wipe Takibi")
        return await self._send_embed(embed)

    async def send_test(self, guild: discord.Guild) -> int:
        now = _utc_now()
        unix = int(now.timestamp())
        embed = discord.Embed(
            title="RUST WIPE DUYURUSU • TEST",
            description="**Arctic Wipe Monitor** test mesajı başarıyla oluşturuldu.",
            colour=discord.Colour.from_rgb(105, 170, 220),
            timestamp=now,
        )
        embed.add_field(name="Sunucu", value="Rusty Moose EU Main", inline=True)
        embed.add_field(name="Durum", value="Test", inline=True)
        embed.add_field(name="Wipe zamanı", value=f"<t:{unix}:F>\n<t:{unix}:R>", inline=False)
        embed.add_field(
            name="Not",
            value="Bu gerçek bir wipe duyurusu değildir. Kanal ve bot izinleri test ediliyor.",
            inline=False,
        )
        embed.set_footer(text="Arctic • Otomatik Wipe Takibi")
        return await self._send_embed(embed, guild=guild)


def _format_health(service: WipeMonitor) -> str:
    lines: list[str] = []
    for spec in MAIN_SERVERS:
        data = service.health.get(spec.key, {})
        status = data.get("ok")
        icon = "🟢" if status is True else "🔴" if status is False else "⚪"
        players = ""
        if status is True and data.get("players") is not None:
            players = f" — {data.get('players')}/{data.get('max_players')}"
        lines.append(f"{icon} **{spec.display_name}**{players}")
    site_status = service.site_health.get("ok")
    site_icon = "🟢" if site_status is True else "🔴" if site_status is False else "⚪"
    lines.append(f"{site_icon} **Survivors.gg resmi wipe sayfası**")
    return "\n".join(lines)


async def register_wipe_system(bot: commands.Bot) -> None:
    if getattr(bot, "_arctic_wipe_registered", False):
        return

    service = WipeMonitor(bot)
    setattr(bot, "_arctic_wipe_registered", True)
    setattr(bot, "_arctic_wipe_service", service)

    @bot.tree.command(name="wipe-durum", description="Otomatik Rust wipe takibinin durumunu gösterir.")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def wipe_durum(interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="Arctic Wipe Monitor",
            description=_format_health(service),
            colour=discord.Colour.from_rgb(105, 170, 220),
        )
        embed.add_field(
            name="Kontrol aralığı",
            value=f"Main sunucular: {WIPE_POLL_SECONDS} sn\nSurvivors.gg wipe sayfası: {SURVIVORS_POLL_SECONDS // 60} dk",
            inline=False,
        )
        channels = service.target_channels(interaction.guild)
        embed.add_field(
            name="Hedef kanal",
            value=channels[0].mention if channels else f"Bulunamadı: `#{WIPE_CHANNEL_NAME}`",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name="wipe-test", description="wipe-katilim kanalına örnek wipe duyurusu gönderir.")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def wipe_test(interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Bu komut sadece sunucuda kullanılabilir.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        sent = await service.send_test(interaction.guild)
        if sent:
            await interaction.followup.send("Wipe test mesajı hedef kanala gönderildi.", ephemeral=True)
        else:
            await interaction.followup.send(
                f"`#{WIPE_CHANNEL_NAME}` kanalı bulunamadı veya botun mesaj/embed izni yok.",
                ephemeral=True,
            )

    @bot.tree.command(name="wipe-kaynaklar", description="Takip edilen Rust wipe kaynaklarını gösterir.")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def wipe_kaynaklar(interaction: discord.Interaction) -> None:
        server_lines = "\n".join(f"• {spec.display_name}" for spec in MAIN_SERVERS)
        text = (
            "**Canlı Main sunucu takibi**\n"
            f"{server_lines}\n\n"
            "**Ek kaynak**\n"
            "• Survivors.gg — resmi Today's Wipes listesi (Main dışındaki Survivors wipe'ları)\n\n"
            "İlk çalıştırmada mevcut wipe sadece başlangıç noktası olarak kaydedilir; eski wipe için mesaj atılmaz."
        )
        await interaction.response.send_message(text, ephemeral=True)

    service.start()
