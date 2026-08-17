from __future__ import annotations

import re

import discord

CHANNEL_NAME = "ses-log"
LEGACY_CHANNEL_NAMES = ("🔊・ses-log", "voice-log")
ALLOWED_ROLE_NAMES = ("👑 Clan Owner", "🛠️ Moderator")
CATEGORY_FALLBACK_NAME = "━━ 👑・YÖNETİM ━━"


def _normalise(value: str) -> str:
    return re.sub(r"[^a-z0-9çğıöşü]+", "", value.casefold())


def _find_management_category(guild: discord.Guild) -> discord.CategoryChannel | None:
    for category in guild.categories:
        name = _normalise(category.name)
        if "yonetim" in name or "management" in name:
            return category
    return None


def _overwrites(guild: discord.Guild) -> dict[discord.Role | discord.Member, discord.PermissionOverwrite]:
    result: dict[discord.Role | discord.Member, discord.PermissionOverwrite] = {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=False,
            read_message_history=False,
            send_messages=False,
        )
    }

    for role_name in ALLOWED_ROLE_NAMES:
        role = discord.utils.get(guild.roles, name=role_name)
        if role is not None:
            result[role] = discord.PermissionOverwrite(
                view_channel=True,
                read_message_history=True,
                send_messages=False,
            )

    if guild.me is not None:
        result[guild.me] = discord.PermissionOverwrite(
            view_channel=True,
            read_message_history=True,
            send_messages=True,
            embed_links=True,
        )

    return result


async def _ensure_channel(guild: discord.Guild) -> discord.TextChannel | None:
    category = _find_management_category(guild)
    if category is None:
        try:
            category = await guild.create_category(
                CATEGORY_FALLBACK_NAME,
                reason="Arctic: ses log yönetim kategorisi",
            )
        except (discord.Forbidden, discord.HTTPException):
            return None

    channel = discord.utils.get(guild.text_channels, name=CHANNEL_NAME)
    if channel is None:
        for old_name in LEGACY_CHANNEL_NAMES:
            channel = discord.utils.get(guild.text_channels, name=old_name)
            if channel is not None:
                break

    try:
        if channel is None:
            channel = await guild.create_text_channel(
                CHANNEL_NAME,
                category=category,
                overwrites=_overwrites(guild),
                topic="Tüm ses kanallarındaki giriş, çıkış ve kanal değişikliklerini kaydeder.",
                reason="Arctic: özel ses-log kanalı",
            )
            return channel

        changes: dict[str, object] = {}
        if channel.name != CHANNEL_NAME:
            changes["name"] = CHANNEL_NAME
        if channel.category_id != category.id:
            changes["category"] = category
        if changes:
            channel = await channel.edit(
                **changes,
                reason="Arctic: ses-log kanalını YÖNETİM alanına taşı",
            )

        # Kanal yalnızca Owner, Moderator ve bot tarafından görülebilir.
        desired = _overwrites(guild)
        allowed_ids = {target.id for target in desired}
        for target in list(channel.overwrites):
            if target.id not in allowed_ids:
                await channel.set_permissions(
                    target,
                    overwrite=None,
                    reason="Arctic: ses-log gizlilik temizliği",
                )
        for target, overwrite in desired.items():
            await channel.set_permissions(
                target,
                overwrite=overwrite,
                reason="Arctic: ses-log gizlilik izinleri",
            )
        return channel
    except (discord.Forbidden, discord.HTTPException):
        return channel


def _member_value(member: discord.Member) -> str:
    return f"{member.mention}\n`{member}`\n`ID: {member.id}`"


async def _log_voice_change(
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
) -> None:
    if before.channel == after.channel:
        return

    channel = await _ensure_channel(member.guild)
    if channel is None:
        return

    if before.channel is None and after.channel is not None:
        embed = discord.Embed(
            title="🟢 Ses Kanalına Girdi",
            colour=discord.Colour.green(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Kullanıcı", value=_member_value(member), inline=False)
        embed.add_field(name="Kanal", value=after.channel.mention, inline=False)
    elif before.channel is not None and after.channel is None:
        embed = discord.Embed(
            title="🔴 Ses Kanalından Çıktı",
            colour=discord.Colour.red(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Kullanıcı", value=_member_value(member), inline=False)
        embed.add_field(name="Kanal", value=before.channel.mention, inline=False)
    elif before.channel is not None and after.channel is not None:
        embed = discord.Embed(
            title="🔁 Ses Kanalı Değiştirdi",
            colour=discord.Colour.gold(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Kullanıcı", value=_member_value(member), inline=False)
        embed.add_field(name="Önce", value=before.channel.mention, inline=True)
        embed.add_field(name="Sonra", value=after.channel.mention, inline=True)
    else:
        return

    if member.display_avatar:
        embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text="Arctic Ses Log")

    try:
        await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
    except (discord.Forbidden, discord.HTTPException):
        pass


def register_voice_log(bot: discord.Client) -> None:
    if getattr(bot, "_arctic_voice_log_registered", False):
        return
    setattr(bot, "_arctic_voice_log_registered", True)

    async def _voice_log_ready() -> None:
        for guild in bot.guilds:
            await _ensure_channel(guild)

    async def _voice_log_state_update(
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        await _log_voice_change(member, before, after)

    bot.add_listener(_voice_log_ready, "on_ready")
    bot.add_listener(_voice_log_state_update, "on_voice_state_update")
