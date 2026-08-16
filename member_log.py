from __future__ import annotations

import json
import re
from pathlib import Path

import discord

CHANNEL_NAME = "gelen-giden"
STATE_FILE = Path(__file__).resolve().parent / ".member_log_channels.json"
CATEGORY_FALLBACK_NAME = "━━ ℹ️・BİLGİ ━━"


def _normalise(value: str) -> str:
    return re.sub(r"[^a-z0-9çğıöşü]+", "", value.casefold())


def _load_state() -> dict[str, int]:
    try:
        raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}

    state: dict[str, int] = {}
    if isinstance(raw, dict):
        for guild_id, channel_id in raw.items():
            try:
                state[str(int(guild_id))] = int(channel_id)
            except (TypeError, ValueError):
                continue
    return state


def _save_state(state: dict[str, int]) -> None:
    try:
        STATE_FILE.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


def _find_info_category(guild: discord.Guild) -> discord.CategoryChannel | None:
    for category in guild.categories:
        normalised = _normalise(category.name)
        if "bilgi" in normalised or normalised.endswith("info") or "information" in normalised:
            return category
    return None


async def _ensure_channel(guild: discord.Guild) -> discord.TextChannel | None:
    state = _load_state()
    saved_id = state.get(str(guild.id))
    if saved_id:
        saved = guild.get_channel(saved_id)
        if isinstance(saved, discord.TextChannel):
            # Kanal bir kere kurulduktan sonra kullanıcının elle yaptığı ayarlara dokunma.
            return saved

    category = _find_info_category(guild)
    if category is None:
        try:
            category = await guild.create_category(
                CATEGORY_FALLBACK_NAME,
                reason="Arctic: gelen-giden bilgi alanı",
            )
        except (discord.Forbidden, discord.HTTPException):
            return None

    # İlk kurulumda mevcut bir gelen-giden kanalı varsa onu kullan.
    existing = discord.utils.get(guild.text_channels, name=CHANNEL_NAME)
    if existing is not None:
        if existing.category_id != category.id:
            try:
                await existing.edit(
                    category=category,
                    reason="Arctic: gelen-giden kanalını BİLGİ alanına taşı",
                )
            except (discord.Forbidden, discord.HTTPException):
                pass
        state[str(guild.id)] = existing.id
        _save_state(state)
        return existing

    bot_member = guild.me
    overwrites: dict[discord.Role | discord.Member, discord.PermissionOverwrite] = {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=True,
            read_message_history=True,
            send_messages=False,
        )
    }
    if bot_member is not None:
        overwrites[bot_member] = discord.PermissionOverwrite(
            view_channel=True,
            read_message_history=True,
            send_messages=True,
            embed_links=True,
        )

    try:
        channel = await guild.create_text_channel(
            CHANNEL_NAME,
            category=category,
            overwrites=overwrites,
            topic="Sunucuya katılan ve ayrılan üyeler burada otomatik olarak gösterilir.",
            reason="Arctic: gelen-giden kanalı",
        )
    except (discord.Forbidden, discord.HTTPException):
        return None

    state[str(guild.id)] = channel.id
    _save_state(state)
    return channel


def _member_label(member: discord.Member) -> str:
    return f"{member.mention}\n`{member}`"


async def _send_join(member: discord.Member) -> None:
    channel = await _ensure_channel(member.guild)
    if channel is None:
        return

    embed = discord.Embed(
        title="🟢 Sunucuya Katıldı",
        description=f"{member.mention} aramıza katıldı. Hoş geldin!",
        colour=discord.Colour.green(),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="Kullanıcı", value=_member_label(member), inline=True)
    embed.add_field(name="Üye Sayısı", value=str(member.guild.member_count or len(member.guild.members)), inline=True)
    embed.set_footer(text=f"Kullanıcı ID: {member.id}")
    if member.display_avatar:
        embed.set_thumbnail(url=member.display_avatar.url)

    try:
        await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
    except (discord.Forbidden, discord.HTTPException):
        pass


async def _send_leave(member: discord.Member) -> None:
    channel = await _ensure_channel(member.guild)
    if channel is None:
        return

    embed = discord.Embed(
        title="🔴 Sunucudan Ayrıldı",
        description=f"**{member.display_name}** sunucudan ayrıldı.",
        colour=discord.Colour.red(),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="Kullanıcı", value=f"`{member}`", inline=True)
    embed.add_field(name="Üye Sayısı", value=str(member.guild.member_count or len(member.guild.members)), inline=True)
    embed.set_footer(text=f"Kullanıcı ID: {member.id}")
    if member.display_avatar:
        embed.set_thumbnail(url=member.display_avatar.url)

    try:
        await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
    except (discord.Forbidden, discord.HTTPException):
        pass


def register_member_log(bot: discord.Client) -> None:
    if getattr(bot, "_arctic_member_log_registered", False):
        return
    setattr(bot, "_arctic_member_log_registered", True)

    async def _member_log_ready() -> None:
        for guild in bot.guilds:
            await _ensure_channel(guild)

    async def _member_log_join(member: discord.Member) -> None:
        await _send_join(member)

    async def _member_log_leave(member: discord.Member) -> None:
        await _send_leave(member)

    bot.add_listener(_member_log_ready, "on_ready")
    bot.add_listener(_member_log_join, "on_member_join")
    bot.add_listener(_member_log_leave, "on_member_remove")
