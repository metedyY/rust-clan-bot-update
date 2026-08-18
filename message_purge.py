from __future__ import annotations

import discord
from discord import app_commands

PURGE_ROLE_NAMES = {"👑 Clan Owner", "🛠️ Moderator"}


def _can_use_purge(interaction: discord.Interaction) -> bool:
    member = interaction.user
    guild = interaction.guild
    if guild is None or not isinstance(member, discord.Member):
        return False
    if member.id == guild.owner_id:
        return True
    if member.guild_permissions.administrator or member.guild_permissions.manage_messages:
        return True
    return any(role.name in PURGE_ROLE_NAMES for role in member.roles)


def register_message_purge(bot: discord.Client) -> None:
    if getattr(bot, "_arctic_message_purge_registered", False):
        return
    setattr(bot, "_arctic_message_purge_registered", True)

    @app_commands.command(name="sil", description="Bu kanaldaki en son mesajları siler.")
    @app_commands.describe(adet="Silinecek son mesaj sayısı (1-100)")
    @app_commands.guild_only()
    async def sil(interaction: discord.Interaction, adet: int) -> None:
        guild = interaction.guild
        member = interaction.user
        channel = interaction.channel

        if guild is None or not isinstance(member, discord.Member):
            await interaction.response.send_message(
                "Bu komut sadece sunucuda kullanılabilir.",
                ephemeral=True,
            )
            return

        if not _can_use_purge(interaction):
            await interaction.response.send_message(
                "Bu komutu yalnızca **Clan Owner**, **Moderator**, sunucu sahibi, Administrator veya **Mesajları Yönet** yetkisi olanlar kullanabilir.",
                ephemeral=True,
            )
            return

        if adet < 1 or adet > 100:
            await interaction.response.send_message(
                "Silinecek mesaj sayısı **1 ile 100** arasında olmalı.",
                ephemeral=True,
            )
            return

        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "Bu komut yalnızca normal yazı kanallarında kullanılabilir.",
                ephemeral=True,
            )
            return

        bot_member = guild.me
        if bot_member is None:
            await interaction.response.send_message(
                "Botun sunucu üyeliği doğrulanamadı.",
                ephemeral=True,
            )
            return

        bot_permissions = channel.permissions_for(bot_member)
        if not bot_permissions.manage_messages or not bot_permissions.read_message_history:
            await interaction.response.send_message(
                "Botun bu kanalda **Mesajları Yönet** ve **Mesaj Geçmişini Oku** yetkileri olmalı.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            deleted = await channel.purge(
                limit=adet,
                reason=f"/sil {adet} | Yetkili: {member} ({member.id})",
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "Mesajlar silinemedi. Botun bu kanaldaki izinlerini kontrol et.",
                ephemeral=True,
            )
            return
        except discord.HTTPException as exc:
            await interaction.followup.send(
                f"Discord mesaj silme işlemini tamamlayamadı: `{exc}`",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"✅ En son **{len(deleted)} mesaj** silindi.",
            ephemeral=True,
        )

    bot.tree.add_command(sil)
