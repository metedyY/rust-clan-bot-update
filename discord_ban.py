from __future__ import annotations

import re

import discord
from discord import app_commands

BAN_ROLE_NAMES = {"👑 Clan Owner", "🛠️ Moderator"}
DISCORD_ID_RE = re.compile(r"^\d{15,22}$")


def _can_use_ban(interaction: discord.Interaction) -> bool:
    member = interaction.user
    guild = interaction.guild
    if guild is None or not isinstance(member, discord.Member):
        return False
    if member.id == guild.owner_id:
        return True
    if member.guild_permissions.administrator:
        return True
    return any(role.name in BAN_ROLE_NAMES for role in member.roles)


def _parse_user_id(value: str) -> int | None:
    cleaned = value.strip()
    if cleaned.startswith("<@") and cleaned.endswith(">"):
        cleaned = cleaned[2:-1]
        if cleaned.startswith("!"):
            cleaned = cleaned[1:]
    if not DISCORD_ID_RE.fullmatch(cleaned):
        return None
    try:
        user_id = int(cleaned)
    except ValueError:
        return None
    return user_id if user_id > 0 else None


def _safe_reason(value: str) -> str:
    reason = " ".join(value.replace("\r", " ").replace("\n", " ").split())
    return (reason or "Kalıcı Discord ban")[:400]


def _hierarchy_error(
    interaction: discord.Interaction,
    target: discord.Member,
) -> str | None:
    guild = interaction.guild
    actor = interaction.user
    if guild is None or not isinstance(actor, discord.Member):
        return "Bu komut sadece sunucuda kullanılabilir."

    if target.id == guild.owner_id:
        return "Sunucu sahibi banlanamaz."
    if target.id == actor.id:
        return "Kendini banlayamazsın."
    if interaction.client.user is not None and target.id == interaction.client.user.id:
        return "Bot kendisini banlayamaz."

    bot_member = guild.me
    if bot_member is None or not bot_member.guild_permissions.ban_members:
        return "Botun **Üyeleri Yasakla (Ban Members)** yetkisi yok."
    if target.top_role >= bot_member.top_role:
        return "Bu kullanıcı botun rolüne eşit veya daha yüksek rolde olduğu için banlanamaz."

    # Sunucu sahibi rol hiyerarşisinden muaftır. Diğer yetkililer kendilerine eşit/üst kişiyi banlayamaz.
    if actor.id != guild.owner_id and target.top_role >= actor.top_role:
        return "Kendi rolüne eşit veya daha yüksek roldeki bir kullanıcıyı banlayamazsın."

    return None


def register_discord_ban(bot: discord.Client) -> None:
    if getattr(bot, "_arctic_discord_ban_registered", False):
        return
    setattr(bot, "_arctic_discord_ban_registered", True)

    ban_group = app_commands.Group(
        name="ban",
        description="Discord sunucusu ban yönetimi.",
    )

    @ban_group.command(
        name="perma",
        description="Discord kullanıcı ID'si ile kullanıcıyı sunucudan kalıcı banlar.",
    )
    @app_commands.guild_only()
    @app_commands.describe(
        oyuncu_id="Banlanacak kullanıcının Discord kullanıcı ID'si",
        sebep="Ban sebebi",
    )
    async def ban_perma(
        interaction: discord.Interaction,
        oyuncu_id: str,
        sebep: str = "Kalıcı ban",
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Bu komut sadece sunucuda kullanılabilir.",
                ephemeral=True,
            )
            return

        if not _can_use_ban(interaction):
            await interaction.response.send_message(
                "Bu komutu yalnızca **Clan Owner**, **Moderator**, sunucu sahibi veya Administrator kullanabilir.",
                ephemeral=True,
            )
            return

        user_id = _parse_user_id(oyuncu_id)
        if user_id is None:
            await interaction.response.send_message(
                "Geçerli bir **Discord kullanıcı ID'si** gir. Kullanıcı etiketini (`<@ID>`) de kullanabilirsin.",
                ephemeral=True,
            )
            return

        if user_id == guild.owner_id:
            await interaction.response.send_message("Sunucu sahibi banlanamaz.", ephemeral=True)
            return
        if user_id == interaction.user.id:
            await interaction.response.send_message("Kendini banlayamazsın.", ephemeral=True)
            return
        if interaction.client.user is not None and user_id == interaction.client.user.id:
            await interaction.response.send_message("Bot kendisini banlayamaz.", ephemeral=True)
            return

        bot_member = guild.me
        if bot_member is None or not bot_member.guild_permissions.ban_members:
            await interaction.response.send_message(
                "Botun **Üyeleri Yasakla (Ban Members)** yetkisi yok.",
                ephemeral=True,
            )
            return

        target_member = guild.get_member(user_id)
        if target_member is not None:
            hierarchy_error = _hierarchy_error(interaction, target_member)
            if hierarchy_error:
                await interaction.response.send_message(hierarchy_error, ephemeral=True)
                return

        reason = _safe_reason(sebep)
        audit_reason = f"{reason} | Yetkili: {interaction.user} ({interaction.user.id})"

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            await guild.ban(
                discord.Object(id=user_id),
                reason=audit_reason[:512],
                delete_message_seconds=0,
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "Ban uygulanamadı. Botun **Ban Members** yetkisini ve rol sırasını kontrol et.",
                ephemeral=True,
            )
            return
        except discord.NotFound:
            await interaction.followup.send(
                "Discord bu kullanıcı ID'sini bulamadı.",
                ephemeral=True,
            )
            return
        except discord.HTTPException as exc:
            await interaction.followup.send(
                f"Discord API ban işlemini tamamlayamadı: `{exc}`",
                ephemeral=True,
            )
            return

        label = target_member.mention if target_member is not None else f"`{user_id}`"
        await interaction.followup.send(
            f"✅ {label} Discord sunucusundan **kalıcı olarak banlandı**.\n"
            f"**Sebep:** {reason}",
            ephemeral=True,
        )

    bot.tree.add_command(ban_group)
