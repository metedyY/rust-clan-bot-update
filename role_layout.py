from __future__ import annotations

import asyncio
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


def _overwrite_matches(
    channel: discord.abc.GuildChannel,
    target: discord.Role | discord.Member,
    **permissions: bool | None,
) -> bool:
    current = channel.overwrites_for(target)
    desired = discord.PermissionOverwrite(**permissions)
    return current.pair() == desired.pair()


async def _set_permissions_if_changed(
    channel: discord.abc.GuildChannel,
    target: discord.Role | discord.Member,
    *,
    reason: str,
    **permissions: bool | None,
) -> bool:
    if _overwrite_matches(channel, target, **permissions):
        return False
    await channel.set_permissions(target, reason=reason, **permissions)
    # İlk kurulumda çok sayıda overwrite değişiyorsa Discord rate limitine yüklenme.
    await asyncio.sleep(0.20)
    return True


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
        needs_edit = (
            main.colour.value != 0x6EA8FE
            or not main.hoist
            or main.mentionable
            or main.permissions.value != discord.Permissions.none().value
        )
        if needs_edit:
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
            if main in member.roles:
                continue
            try:
                await member.add_roles(main, reason="Arctic: eski Üye rolünden ARC MAIN KADRO'ya geçiş")
                await asyncio.sleep(0.15)
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
        needs_edit = (
            guest.colour.value != 0x95A5A6
            or guest.hoist
            or guest.mentionable
            or guest.permissions.value != discord.Permissions.none().value
        )
        if needs_edit:
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
        needs_edit = (
            role.colour.value != discord.Colour.default().value
            or role.hoist
            or role.mentionable
            or role.permissions.value != discord.Permissions.none().value
        )
        if not needs_edit:
            continue
        try:
            await role.edit(
                colour=discord.Colour.default(),
                hoist=False,
                mentionable=False,
                permissions=discord.Permissions.none(),
                reason="Arctic: görev rolü sadece kadro sınıflandırması için",
            )
            await asyncio.sleep(0.15)
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
            await _set_permissions_if_changed(
                general, guild.default_role,
                view_channel=False,
                reason="Arctic: Genel Alan rol bazlı",
            )
            await _set_permissions_if_changed(
                general, guest,
                view_channel=True,
                read_message_history=True,
                send_messages=True,
                reason="Arctic: Misafir Genel Alan",
            )
            for role in member_roles:
                await _set_permissions_if_changed(
                    general, role,
                    view_channel=True,
                    reason="Arctic: Kadro Genel Alan",
                )
        except (discord.Forbidden, discord.HTTPException):
            pass

    voice_category = discord.utils.get(guild.categories, name=VOICE_CATEGORY_NAME)
    if voice_category is not None:
        try:
            await _set_permissions_if_changed(
                voice_category, guild.default_role,
                view_channel=False,
                connect=False,
                reason="Arctic: Ses alanı rol bazlı",
            )
            await _set_permissions_if_changed(
                voice_category, guest,
                view_channel=True,
                connect=True,
                speak=True,
                stream=True,
                reason="Arctic: Misafir ses erişimi",
            )
            for role in member_roles:
                await _set_permissions_if_changed(
                    voice_category, role,
                    view_channel=True,
                    connect=True,
                    speak=True,
                    stream=True,
                    reason="Arctic: Kadro ses erişimi",
                )
        except (discord.Forbidden, discord.HTTPException):
            pass

        for channel in voice_category.voice_channels:
            try:
                await _set_permissions_if_changed(
                    channel, guild.default_role,
                    view_channel=False,
                    connect=False,
                    reason="Arctic: Ses rol bazlı",
                )
                await _set_permissions_if_changed(
                    channel, guest,
                    view_channel=True,
                    connect=True,
                    speak=True,
                    stream=True,
                    reason="Arctic: Misafir ses erişimi",
                )
                for role in member_roles:
                    await _set_permissions_if_changed(
                        channel, role,
                        view_channel=True,
                        connect=True,
                        speak=True,
                        stream=True,
                        reason="Arctic: Kadro ses erişimi",
                    )
            except (discord.Forbidden, discord.HTTPException):
                continue

    # Misafir yalnızca Genel Alan + Ses Kanalları görsün.
    for category in guild.categories:
        if category.name in {GENERAL_CATEGORY_NAME, VOICE_CATEGORY_NAME}:
            continue
        try:
            await _set_permissions_if_changed(
                category, guest,
                view_channel=False,
                reason="Arctic: Misafir erişim sınırı",
            )
        except (discord.Forbidden, discord.HTTPException):
            continue

    application = discord.utils.get(guild.categories, name=APPLICATION_CATEGORY_NAME)
    if application is not None:
        try:
            await _set_permissions_if_changed(
                application, guest,
                view_channel=False,
                reason="Arctic: Misafir başvuru alanını görmez",
            )
            await _set_permissions_if_changed(
                application, main,
                view_channel=False,
                reason="Arctic: Kadro başvuru alanını görmez",
            )
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
