from __future__ import annotations

import asyncio
import re

import discord

from ticket_system import (
    TicketManagementView as BaseTicketManagementView,
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
MAIN_ROLE_NAME = "⚡ ARC MAIN KADRO"


def _embed_field(embed: discord.Embed, name: str) -> str | None:
    for field in embed.fields:
        if field.name.casefold() == name.casefold():
            return str(field.value).strip()
    return None


def _application_data_from_message(message: discord.Message | None) -> tuple[int, str, str] | None:
    if message is None or not message.embeds:
        return None

    embed = message.embeds[0]
    description = embed.description or ""
    user_match = re.search(r"Kullanıcı ID:\s*`?(\d{15,22})`?", description, flags=re.I)
    applicant_name = _embed_field(embed, "İsim")
    age = _embed_field(embed, "Yaş")

    if not user_match or not applicant_name or not age:
        return None

    return int(user_match.group(1)), applicant_name, age


async def _rename_after_accept(
    guild: discord.Guild,
    user_id: int,
    applicant_name: str,
    age: str,
    had_main_role: bool,
) -> None:
    # Kabul callback'inin rolü vermesini bekle. Red/close işleminde rol gelmeyeceği için nick değişmez.
    for _ in range(8):
        await asyncio.sleep(0.75)
        member = guild.get_member(user_id)
        if member is None:
            try:
                member = await guild.fetch_member(user_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return

        main_role = discord.utils.get(guild.roles, name=MAIN_ROLE_NAME)
        if main_role is None:
            return

        has_main_role = main_role in member.roles
        if has_main_role and not had_main_role:
            clean_name = re.sub(r"\s+", " ", applicant_name).strip().strip("/")
            clean_age = re.sub(r"\D", "", age)[:3]
            if not clean_name or not clean_age:
                return

            nickname = f"{clean_name}/{clean_age}"[:32]
            try:
                await member.edit(
                    nick=nickname,
                    reason="Arctic: kabul edilen başvuruda İsim/Yaş formatı",
                )
            except (discord.Forbidden, discord.HTTPException):
                pass
            return


class TicketManagementView(BaseTicketManagementView):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        allowed = await super().interaction_check(interaction)
        if not allowed:
            return False

        guild = interaction.guild
        if guild is None:
            return True

        data = _application_data_from_message(interaction.message)
        if data is None:
            return True

        user_id, applicant_name, age = data
        member = guild.get_member(user_id)
        main_role = discord.utils.get(guild.roles, name=MAIN_ROLE_NAME)
        had_main_role = bool(member and main_role and main_role in member.roles)

        # Hangi butonun base view'da "Kabul" olduğunu bilmeye ihtiyaç yok:
        # işlemden sonra kişi ana kadro rolünü yeni aldıysa nick otomatik değiştirilir.
        asyncio.create_task(
            _rename_after_accept(guild, user_id, applicant_name, age, had_main_role)
        )
        return True


class ApplicationModal(discord.ui.Modal, title="Arctic Klan Başvurusu"):
    applicant_name = discord.ui.TextInput(
        label="İsmin",
        placeholder="Örn: Mahmut",
        min_length=2,
        max_length=32,
    )
    age = discord.ui.TextInput(
        label="Yaşın",
        placeholder="Örn: 31",
        min_length=1,
        max_length=3,
    )
    rust_role = discord.ui.TextInput(
        label="Rust saatin / Ana rolün",
        placeholder="Örn: 2500 saat / Roamer",
        min_length=3,
        max_length=100,
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

        applicant_name = re.sub(r"\s+", " ", str(self.applicant_name.value)).strip().strip("/")
        age = str(self.age.value).strip()
        if not applicant_name:
            await interaction.response.send_message("❌ Geçerli bir isim girmelisin.", ephemeral=True)
            return
        if not re.fullmatch(r"\d{1,3}", age):
            await interaction.response.send_message("❌ Yaş alanına sadece sayı girmelisin. Örnek: `31`", ephemeral=True)
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
            embed.add_field(name="İsim", value=applicant_name, inline=True)
            embed.add_field(name="Yaş", value=age, inline=True)
            embed.add_field(name="Rust Saati / Ana Rol", value=str(self.rust_role.value), inline=False)
            embed.add_field(name="Steam Profili", value=f"[Profili Aç]({steam_url})\n`{steam_url}`", inline=False)
            embed.add_field(name="Aktiflik / Oyun Tarzı", value=str(self.profile.value), inline=False)
            embed.set_footer(text="Kabul edildiğinde sunucu adı otomatik İsim/Yaş formatına çevrilir.")

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
            "• İsim\n"
            "• Yaş\n"
            "• Rust saati / Ana rol (Örn: `2500 saat / Roamer`)\n"
            "• Steam profil linki\n"
            "  Örnek: `https://steamcommunity.com/id/kullaniciadi`\n"
            "• Günlük aktiflik + oyun tarzın hakkında kısa bilgi\n\n"
            "**Kabul sonrası:** Sunucudaki adın otomatik `İsim/Yaş` formatına çevrilir. Örnek: `Mahmut/31`\n\n"
            "**Not:** Aynı anda yalnızca bir açık başvurun olabilir."
        ),
        colour=discord.Colour.blue(),
    )
    embed.set_footer(text="Arctic Klan Başvuru Sistemi")
    return await channel.send(embed=embed, view=ApplicationPanelView())
