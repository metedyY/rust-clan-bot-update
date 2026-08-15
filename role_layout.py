from __future__ import annotations

import logging

import discord

log = logging.getLogger("rust-setup-bot.roles")

MAIN_ROLE_NAME = "⚡ ARC MAIN KADRO"
OLD_MAIN_ROLE_NAMES = ("👤 Üye", "👤 Member")
GUEST_ROLE_NAME = "👋 Misafir"
OLD_GUEST_ROLE_NAMES = ("🌐 Guest", "Guest", "Misafir")
TASK_ROLE_NAMES = ("🎯 Roamer", "🏗️ Builder", "⛏️ Farmer")
STAFF_ROLE_NAMES = (
    "👑 Clan Owner",
    "🛡️ Co-Owner",
    "⚔️ Clan Leader",
    "🧭 Co-Leader",
    "🛠️ Moderator",
    "📣 Recruiter",
)
GENERAL_CATEGORY_NAME = "━━ 🌍・GENEL ALAN ━━"
VOICE_CATEGORY_NAME = "━━ 🔊・SES KANALLARI ━━"
APPLICATION_CATEGORY_NAME = "━━ 🎫・BAŞVURULAR ━━"


def _role(guild: discord.Guild, name: str) -> discord.Role | None:
    return discord.utils.get(guild.roles, name=name)


async def _ensure_main_role(guild: discord.Guild) -> discord.Role:
    main = _role(guild, MAIN_ROLE_NAME)
    old_roles = [role for name in OLD_MAIN_ROLE_NAMES if (role := _role(guild, name)) is not None]

    if main is None and old_roles:
        candidate = old_roles.pop(0)
        if not candidate.managed:
            try:
                main = await candidate.edit(
                    name=MAIN_ROLE_NAME,
                    colour=discord.Colour(0x6EA8FE),
                    hoist=True,
                    mentionable=False,
                    permissions=discord.Permissions.none(),
                    reason="Arctic: ana kadro rolüne geçir",
                )
            except discord.Forbidden:
                main = None

    if main is None:
        main = await guild.create_role(
            name=MAIN_ROLE_NAME,
            colour=discord.Colour(0x6EA8FE),
            hoist=True,
            mentionable=False,
            permissions=discord.Permissions.none(),
            reason="Arctic: ana kadro rolü oluştur",
        )
    elif not main.managed:
        try:
            main = await main.edit(
                colour=discord.Colour(0x6EA8FE),
                hoist=True,
                mentionable=False,
                permissions=discord.Permissions.none(),
                reason="Arctic: ana kadro rolünü güncelle",
            )
        except discord.Forbidden:
            pass

    # Eski Üye rolü ile yeni rol aynı anda varsa üyeleri otomatik taşı.
    for old_name in OLD_MAIN_ROLE_NAMES:
        old = _role(guild, old_name)
        if old is None or old.id == main.id:
            continue
        for member in list(old.members):
            try:
                await member.add_roles(main, reason="Arctic: eski Üye rolünden ARC MAIN KADRO'ya geçiş")
            except (discord.Forbidden, discord.HTTPException):
                continue
        if not old.managed:
            try:
                await old.delete(reason="Arctic: eski Üye rolü kaldırıldı")
            except (discord.Forbidden, discord.HTTPException):
                pass

    return main


async def _ensure_guest_role(guild: discord.Guild) -> discord.Role:
    guest = _role(guild, GUEST_ROLE_NAME)
    old_roles = [role for name in OLD_GUEST_ROLE_NAMES if (role := _role(guild, name)) is not None]

    if guest is None and old_roles:
        candidate = old_roles.pop(0)
        if not candidate.managed:
            try:
                guest = await candidate.edit(
                    name=GUEST_ROLE_NAME,
                    colour=discord.Colour(0x95A5A6),
                    hoist=False,
                    mentionable=False,
                    permissions=discord.Permissions.none(),
                    reason="Arctic: Misafir rolünü düzenle",
                )
            except discord.Forbidden:
                guest = None

    if guest is None:
        guest = await guild.create_role(
            name=GUEST_ROLE_NAME,
            colour=discord.Colour(0x95A5A6),
            hoist=False,
            mentionable=False,
            permissions=discord.Permissions.none(),
            reason="Arctic: Misafir rolü oluştur",
        )
    elif not guest.managed:
        try:
            guest = await guest.edit(
                colour=discord.Colour(0x95A5A6),
                hoist=False,
                mentionable=False,
                permissions=discord.Permissions.none(),
                reason="Arctic: Misafir rolünü güncelle",
            )
        except discord.Forbidden:
            pass

    return guest


async def _normalize_task_roles(guild: discord.Guild, main: discord.Role) -> None:
    tasks: list[discord.Role] = []
    for name in TASK_ROLE_NAMES:
        role = _role(guild, name)
        if role is None or role.managed:
            continue
        tasks.append(role)
        try:
            await role.edit(
                colour=discord.Colour.default(),
                hoist=False,
                mentionable=False,
                permissions=discord.Permissions.none(),
                reason="Arctic: görev rolü sadece kadro sınıflandırması için",
            )
        except discord.Forbidden:
            pass

    # Ana rolü görev rollerinin üstüne taşı: kullanıcı adı/üye listesi tek ana rolden görünür.
    if tasks and not main.managed:
        try:
            highest_task = max(role.position for role in tasks)
            target = min(highest_task + 1, guild.me.top_role.position - 1) if guild.me else highest_task + 1
            if target > 0 and main.position != target:
                await guild.edit_role_positions(positions={main: target}, reason="Arctic: ARC MAIN KADRO üstte")
        except (discord.Forbidden, discord.HTTPException):
            pass


async def _apply_visibility(guild: discord.Guild, main: discord.Role, guest: discord.Role) -> None:
    member_roles = [main]
    for name in (*STAFF_ROLE_NAMES, *TASK_ROLE_NAMES):
        role = _role(guild, name)
        if role is not None:
            member_roles.append(role)

    general = discord.utils.get(guild.categories, name=GENERAL_CATEGORY_NAME)
    if general is not None:
        try:
            await general.set_permissions(guild.default_role, view_channel=False, reason="Arctic: Genel Alan rol bazlı")
            await general.set_permissions(guest, view_channel=True, read_message_history=True, send_messages=True, reason="Arctic: Misafir Genel Alan")
            for role in member_roles:
                await general.set_permissions(role, view_channel=True, reason="Arctic: Kadro Genel Alan")
        except (discord.Forbidden, discord.HTTPException):
            pass

    voice_category = discord.utils.get(guild.categories, name=VOICE_CATEGORY_NAME)
    if voice_category is not None:
        # Kategori de gizli olsun; kanal bazında Misafir + kadro erişir.
        try:
            await voice_category.set_permissions(guild.default_role, view_channel=False, connect=False, reason="Arctic: Ses alanı rol bazlı")
            await voice_category.set_permissions(guest, view_channel=True, connect=True, speak=True, stream=True, reason="Arctic: Misafir ses erişimi")
            for role in member_roles:
                await voice_category.set_permissions(role, view_channel=True, connect=True, speak=True, stream=True, reason="Arctic: Kadro ses erişimi")
        except (discord.Forbidden, discord.HTTPException):
            pass

        for channel in voice_category.voice_channels:
            try:
                await channel.set_permissions(guild.default_role, view_channel=False, connect=False, reason="Arctic: Ses rol bazlı")
                await channel.set_permissions(guest, view_channel=True, connect=True, speak=True, stream=True, reason="Arctic: Misafir ses erişimi")
                for role in member_roles:
                    await channel.set_permissions(role, view_channel=True, connect=True, speak=True, stream=True, reason="Arctic: Kadro ses erişimi")
            except (discord.Forbidden, discord.HTTPException):
                continue

    # Misafir yalnızca Genel Alan + Ses Kanalları görsün.
    for category in guild.categories:
        if category.name in {GENERAL_CATEGORY_NAME, VOICE_CATEGORY_NAME}:
            continue
        try:
            await category.set_permissions(guest, view_channel=False, reason="Arctic: Misafir erişim sınırı")
        except (discord.Forbidden, discord.HTTPException):
            continue

    application = discord.utils.get(guild.categories, name=APPLICATION_CATEGORY_NAME)
    if application is not None:
        try:
            await application.set_permissions(guest, view_channel=False, reason="Arctic: Misafir başvuru alanını görmez")
            await application.set_permissions(main, view_channel=False, reason="Arctic: Kadro başvuru alanını görmez")
        except (discord.Forbidden, discord.HTTPException):
            pass


async def apply_arc_role_layout(guild: discord.Guild) -> None:
    """ARC ana kadro + gizli görev rolleri + kontrollü Misafir görünürlüğünü uygular."""
    try:
        main = await _ensure_main_role(guild)
        guest = await _ensure_guest_role(guild)
        await _normalize_task_roles(guild, main)
        await _apply_visibility(guild, main, guest)
        log.info("ARC rol düzeni uygulandı: %s", guild.name)
    except discord.Forbidden:
        log.warning("ARC rol düzeni uygulanamadı: bot rol/kanal izinleri yetersiz (%s)", guild.name)
    except discord.HTTPException as exc:
        log.warning("ARC rol düzeni Discord API hatası [%s]: %s", guild.name, exc)
