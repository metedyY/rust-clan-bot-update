from __future__ import annotations

import re
import unicodedata

import discord

CHANNEL_NAME = "ses-log"
LEGACY_CHANNEL_NAMES = ("🔊・ses-log", "voice-log")
ALLOWED_ROLE_NAMES = ("👑 Clan Owner", "🛠️ Moderator")
TOPIC = "Tüm ses kanallarındaki giriş, çıkış ve kanal değişikliklerini kaydeder."
MANAGEMENT_HINT_CHANNELS = {
    "yonetimsohbeti",
    "basvurudegerlendirme",
    "yetkililog",
}


def _normalise(value: str) -> str:
    # YÖNETİM / Yönetim / yonetim gibi Türkçe karakterli adları aynı biçime getir.
    folded = unicodedata.normalize("NFKD", value.casefold()).replace("ı", "i")
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", folded)


def _is_management_category(category: discord.CategoryChannel) -> bool:
    name = _normalise(category.name)
    return "yonetim" in name or "management" in name


def _category_score(category: discord.CategoryChannel) -> int:
    # Gerçek/orijinal YÖNETİM kategorisini içindeki bilinen kanallardan ayırt et.
    child_names = {_normalise(channel.name) for channel in category.channels}
    hints = len(child_names & MANAGEMENT_HINT_CHANNELS)
    return hints * 100 + len(category.channels)


def _find_management_category(guild: discord.Guild) -> discord.CategoryChannel | None:
    matches = [category for category in guild.categories if _is_management_category(category)]
    if not matches:
        return None

    # Önce yönetim-sohbeti / başvuru-değerlendirme / yetkili-log içeren gerçek kategori.
    # Eşitlikte Discord sıralamasında daha yukarıdaki kategori tercih edilir.
    return max(matches, key=lambda category: (_category_score(category), -category.position))


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


def _overwrite_matches(
    channel: discord.TextChannel,
    target: discord.Role | discord.Member,
    desired: discord.PermissionOverwrite,
) -> bool:
    return channel.overwrites_for(target).pair() == desired.pair()


def _find_existing_log_channel(guild: discord.Guild) -> discord.TextChannel | None:
    wanted = {_normalise(CHANNEL_NAME), *(_normalise(name) for name in LEGACY_CHANNEL_NAMES)}
    for channel in guild.text_channels:
        if _normalise(channel.name) in wanted:
            return channel
    return None


async def _cleanup_duplicate_management_categories(
    guild: discord.Guild,
    primary: discord.CategoryChannel,
) -> None:
    # Önceki hatalı sürümün oluşturduğu boş YÖNETİM kopyalarını güvenle temizle.
    # İçinde başka kanal bulunan kategorilere dokunulmaz.
    for category in list(guild.categories):
        if category.id == primary.id or not _is_management_category(category):
            continue
        if category.channels:
            continue
        try:
            await category.delete(reason="Arctic: hatalı oluşturulan boş YÖNETİM kopyasını temizle")
        except (discord.Forbidden, discord.HTTPException):
            pass


async def _ensure_channel(guild: discord.Guild) -> discord.TextChannel | None:
    category = _find_management_category(guild)

    # Kritik: mevcut YÖNETİM kategorisi bulunamazsa YENİ kategori oluşturma.
    # Böylece hiçbir ses olayı sınırsız kategori üretemez.
    if category is None:
        return None

    channel = _find_existing_log_channel(guild)

    try:
        if channel is None:
            channel = await guild.create_text_channel(
                CHANNEL_NAME,
                category=category,
                overwrites=_overwrites(guild),
                topic=TOPIC,
                reason="Arctic: özel ses-log kanalı",
            )
        else:
            changes: dict[str, object] = {}
            if channel.name != CHANNEL_NAME:
                changes["name"] = CHANNEL_NAME
            if channel.category_id != category.id:
                changes["category"] = category
            if channel.topic != TOPIC:
                changes["topic"] = TOPIC
            if changes:
                channel = await channel.edit(
                    **changes,
                    reason="Arctic: ses-log kanalını mevcut YÖNETİM kategorisinde tut",
                )

        # Kanal yalnızca Owner, Moderator ve bot tarafından görülebilir.
        desired = _overwrites(guild)
        allowed_ids = {target.id for target in desired}

        for target in list(channel.overwrites):
            if target.id in allowed_ids:
                continue
            await channel.set_permissions(
                target,
                overwrite=None,
                reason="Arctic: ses-log gizlilik temizliği",
            )

        for target, overwrite in desired.items():
            if _overwrite_matches(channel, target, overwrite):
                continue
            await channel.set_permissions(
                target,
                overwrite=overwrite,
                reason="Arctic: ses-log gizlilik izinleri",
            )

        # ses-log gerçek kategoriye taşındıktan sonra boş kalan hatalı kopyaları sil.
        await _cleanup_duplicate_management_categories(guild, category)
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
        await channel.send(
            embed=embed,
            allowed_mentions=discord.AllowedMentions.none(),
        )
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
