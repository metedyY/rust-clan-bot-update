from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta, timezone

import discord
import wipe_monitor as base

# Kullanıcının istediği EU Main listesi.
# Survivors.gg Main ve Atlas EU 2X Main kaldırıldı; Rustoria EU Main eklendi.
base.MAIN_SERVERS = (
    base.ServerSpec(
        "rustafied-eu-main", "Rustafied EU Main", "Rustafied",
        "eumain.rustafied.com", 28015, 28018, "https://www.rustafied.com/server",
    ),
    base.ServerSpec(
        "rustopia-eu-main", "Rustopia EU Main", "Rustopia",
        "eumain.rustopia.gg", 28015, 28010, "https://rustopia.gg/",
    ),
    base.ServerSpec(
        "rustymoose-eu-main", "Rusty Moose EU Main", "Rusty Moose",
        "main.eu.moose.gg", 28010, 28015, "https://moose.gg/",
    ),
    base.ServerSpec(
        "rustoria-eu-main", "Rustoria EU Main", "Rustoria",
        "main.rustoria.uk", 28010, 28015, "https://rustoria.co/servers",
    ),
)


def _last_sunday(year: int, month: int) -> date:
    last = date(year, month, calendar.monthrange(year, month)[1])
    return last - timedelta(days=(last.weekday() - 6) % 7)


def _uk_offset(d: date) -> int:
    return 1 if _last_sunday(d.year, 3) <= d < _last_sunday(d.year, 10) else 0


def _local_to_utc(d: date, hour: int, offset: int) -> datetime:
    tz = timezone(timedelta(hours=offset))
    return datetime(d.year, d.month, d.day, hour, 0, tzinfo=tz).astimezone(timezone.utc)


def _next_thursday_main(now: datetime) -> datetime:
    # Rustafied / Rustopia / Rusty Moose / Rustoria EU Main:
    # normal Perşembe 15:00 London; ayın ilk Perşembesi force wipe saati yaklaşık 19:00 London.
    for step in range(40):
        d = (now - timedelta(days=1)).date() + timedelta(days=step)
        if d.weekday() != 3:
            continue
        hour = 19 if d.day <= 7 else 15
        candidate = _local_to_utc(d, hour, _uk_offset(d))
        if candidate > now:
            return candidate
    return now + timedelta(days=7)


def next_wipe(spec: base.ServerSpec, now: datetime) -> datetime:
    return _next_thursday_main(now)


def _format_health_v2(service: base.WipeMonitor) -> str:
    now = base._utc_now()
    lines: list[str] = []
    for spec in base.MAIN_SERVERS:
        data = service.health.get(spec.key, {})
        status = data.get("ok")
        icon = "🟢" if status is True else "🔴" if status is False else "⚪"
        players = ""
        if status is True and data.get("players") is not None:
            players = f" — {data.get('players')}/{data.get('max_players')}"
        wipe_at = int(next_wipe(spec, now).timestamp())
        lines.append(f"{icon} **{spec.display_name}**{players}")
        lines.append(f"└ ⏳ Sonraki wipe: <t:{wipe_at}:R> • <t:{wipe_at}:f>")
    # Survivors.gg resmi wipe sayfası sağlık satırı panelde gösterilmez.
    return "\n".join(lines)


base._format_health = _format_health_v2


def _build_status_embed_v2(self: base.WipeMonitor) -> discord.Embed:
    now = base._utc_now()
    unix = int(now.timestamp())
    embed = discord.Embed(
        title="Arctic Wipe Takibi",
        description=(
            "Bu panel **otomatik çalışır ve sürekli güncellenir.**\n"
            "Bir sunucu gerçekten wipe olduğunda bu kanala ayrıca duyuru düşer."
        ),
        colour=discord.Colour.from_rgb(105, 170, 220),
    )
    embed.add_field(name="Canlı takip ve wipe sayaçları", value=_format_health_v2(self), inline=False)
    embed.add_field(name="Kontrol aralığı", value=f"Sunucular: {base.WIPE_POLL_SECONDS} sn", inline=True)
    embed.add_field(name="Son kontrol", value=f"<t:{unix}:R>", inline=True)
    embed.set_footer(
        text="Arctic • Sayaç planlanan wipe saatidir; gerçek wipe canlı sunucu verisiyle doğrulanır."
    )
    return embed


base.WipeMonitor._build_status_embed = _build_status_embed_v2
register_wipe_system = base.register_wipe_system
