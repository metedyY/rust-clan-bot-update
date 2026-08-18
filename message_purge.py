from __future__ import annotations

import discord
from discord import app_commands


@app_commands.command(name="sil", description="Bu kanaldaki son mesajları siler.")
@app_commands.describe(adet="Silinecek mesaj sayısı (1-100)")
@app_commands.guild_only()
async def sil(interaction: discord.Interaction, adet: int):
    if not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("Bu komut sunucuda kullanılabilir.", ephemeral=True)
        return

    member = interaction.user
    if not (member.guild_permissions.manage_messages or member.guild_permissions.administrator or member.guild.owner_id == member.id):
        await interaction.response.send_message("Bu komut için Mesajları Yönet yetkisi gerekir.", ephemeral=True)
        return

    if adet < 1 or adet > 100:
        await interaction.response.send_message("1 ile 100 arasında bir sayı gir.", ephemeral=True)
        return

    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message("Bu kanal desteklenmiyor.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    deleted = await channel.purge(limit=adet, reason=f"/sil kullanıldı: {interaction.user}")
    await interaction.followup.send(f"✅ {len(deleted)} mesaj silindi.", ephemeral=True)


def register_message_purge(bot):
    bot.tree.add_command(sil)
