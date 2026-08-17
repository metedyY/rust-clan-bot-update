import discord

LOG_CHANNEL_NAME = "🔊・ses-log"
ALLOWED_ROLES = {"👑 Clan Owner", "🛠️ Moderator"}


async def get_or_create_voice_log_channel(guild: discord.Guild):
    channel = discord.utils.get(guild.text_channels, name=LOG_CHANNEL_NAME)
    if channel:
        return channel

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
    }

    for role in guild.roles:
        if role.name in ALLOWED_ROLES:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True,
                read_message_history=True,
                send_messages=True,
            )

    return await guild.create_text_channel(
        LOG_CHANNEL_NAME,
        overwrites=overwrites,
        reason="Arctic voice log channel",
    )


async def log_voice_change(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    channel = await get_or_create_voice_log_channel(member.guild)

    if before.channel is None and after.channel is not None:
        text = f"🟢 **{member}** ses kanalına girdi: `{after.channel.name}`"
    elif before.channel is not None and after.channel is None:
        text = f"🔴 **{member}** ses kanalından çıktı: `{before.channel.name}`"
    elif before.channel != after.channel:
        text = f"🔁 **{member}** taşındı: `{before.channel.name}` ➜ `{after.channel.name}`"
    else:
        return

    await channel.send(text)
