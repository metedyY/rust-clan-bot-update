from __future__ import annotations

import re

import discord

from ticket_system import (
    TicketManagementView,
    ensure_ticket_category,
    find_existing_ticket,
    get_ticket_staff_roles,
    make_ticket_topic,
    slugify_channel_name,
    ticket_overwrites,
)


STEAM_EXAMPLE = "https://steamcommunity.com/id/kullaniciadi"
STEAM_RE = re.compile(
    r"^https?://(?:www\.)?steamcommunity\.com/(?:id|profiles)/[^/\s?#]+/?(?:[?#].*)?$",
    flags=re.I,
)


class ApplicationModal(discord.ui.Modal, title="Arctic Klan Başvurusu"):
    age = discord.ui.TextInput(
        label="Yaşın",
        placeholder="Örn: 18",
        min_length=1,
        max_length=3,
    )
    rust_hours = discord.ui.TextInput(
        label="Rust saatin",
        placeholder="Örn: 2500 saat",
        min_length=1,
        max_length=40,
    )
    main_role = discord.ui.TextInput(
        label="Ana rolün",
        placeholder="Roamer / Builder / Farmer",
        min_length=2,
        max_length=60,
    )
    steam_profile = discord.ui.TextInput(
        label="Steam profil linkin",
        placeholder=f"Örn: {STEAM_EXAMPLE}",
        min_length=20,
        max_length=200,
    )
    profile = discord.ui.TextInput(
        label="Aktiflik ve oyun tarzın",
        placeholder="Örn: Günde 5-6 saat aktifim. Roamer ağırlıklı oynuyorum.",
        style=discord.TextStyle.paragraph,
        min_length=10,
        max_length=700,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "Bu başvuru sadece bir sunucuda kullanılabilir.",
                ephemeral=True,
            )
            return

        existing = find_existing_ticket(guild, interaction.user.id)
        if existing is not None:
            await interaction.response.send_message(
                f"Zaten açık bir başvurun var: {existing.mention}",
                ephemeral=True,
            )
            return

        steam_url = str(self.steam_profile.value).strip()
        if not STEAM_RE.match(steam_url):
            await interaction.response.send_message(
                f"❌ Geçerli bir Steam profil linki girmelisin. Örnek: `{STEAM_EXAMPLE}`",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            category = await ensure_ticket_category(guild)
            username = slugify_channel_name(interaction.user.display_name)
            channel_name = f"basvuru-{username}-{str(interaction.user.id)[-4:]}"
            channel = await guild.create_text_channel(
                channel_name,
                category=category,
                topic=make_ticket_topic(interaction.user.id),
                overwrites=ticket_overwrites(guild, interaction.user),
                reason=f"Rust Clan başvurusu: {interaction.user}",
            )

            embed = discord.Embed(
                title="Yeni Klan Başvurusu",
                description=(
                    f"Başvuran: {interaction.user.mention}\n"
                    f"Discord: **{interaction.user}**\n"
                    f"Kullanıcı ID: `{interaction.user.id}`"
                ),
                colour=discord.Colour.orange(),
            )
            embed.add_field(name="Yaş", value=str(self.age.value), inline=True)
            embed.add_field(name="Rust Saati", value=str(self.rust_hours.value), inline=True)
            embed.add_field(name="Ana Rol", value=str(self.main_role.value), inline=True)
            embed.add_field(name="Steam Profili", value=f"[Profili Aç]({steam_url})\n`{steam_url}`", inline=False)
            embed.add_field(name="Aktiflik / Oyun Tarzı", value=str(self.profile.value), inline=False)
            embed.set_footer(text="Yetkililer başvuruyu kabul edebilir, reddedebilir veya kapatabilir.")

            notify_roles = [
                role for role in get_ticket_staff_roles(guild)
                if role.name in {"📣 Recruiter", "🛠️ Moderator"}
            ]
            staff_ping = " ".join(role.mention for role in notify_roles)
            header = f"{interaction.user.mention} başvurun açıldı."
            if staff_ping:
                header += f"\n{staff_ping} yeni başvuru var."

            await channel.send(
                content=header,
                embed=embed,
                view=TicketManagementView(),
                allowed_mentions=discord.AllowedMentions(users=True, roles=True),
            )
            await interaction.followup.send(
                f"✅ Başvurun oluşturuldu: {channel.mention}",
                ephemeral=True,
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Ticket oluşturamadım. Botta **Kanalları Yönet** ve gerekli kanal izinleri olmalı.",
                ephemeral=True,
            )
        except discord.HTTPException as exc:
            await interaction.followup.send(
                f"❌ Discord API hatası: `{exc}`",
                ephemeral=True,
            )


class ApplicationPanelView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Başvuru Aç",
        style=discord.ButtonStyle.success,
        custom_id="rust:application:open",
    )
    async def open_application(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Bu buton sadece sunucuda kullanılabilir.",
                ephemeral=True,
            )
            return

        existing = find_existing_ticket(guild, interaction.user.id)
        if existing is not None:
            await interaction.response.send_message(
                f"Zaten açık bir başvurun var: {existing.mention}",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(ApplicationModal())


async def send_application_panel(channel: discord.TextChannel) -> discord.Message:
    embed = discord.Embed(
        title="Arctic Klan Başvurusu",
        description=(
            "Klanımıza katılmak için aşağıdaki **Başvuru Aç** butonunu kullan.\n\n"
            "Başvurunu tamamladıktan sonra sadece senin ve yetkililerin görebileceği özel bir başvuru kanalı açılır.\n\n"
            "**Başvuru Bilgileri**\n"
            "• Yaş\n"
            "• Rust saati\n"
            "• Ana rol (Roamer / Builder / Farmer vb.)\n"
            "• Steam profil linki\n"
            "  Örnek: `https://steamcommunity.com/id/kullaniciadi`\n"
            "• Günlük aktiflik + kendin ve oyun tarzın hakkında kısa bilgi\n\n"
            "**Not:** Aynı anda yalnızca bir açık başvurun olabilir."
        ),
        colour=discord.Colour.blue(),
    )
    embed.set_footer(text="Arctic Klan Başvuru Sistemi")
    return await channel.send(embed=embed, view=ApplicationPanelView())
