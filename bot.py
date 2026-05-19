import re
import discord
from discord.ext import commands
from discord import app_commands
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN      = os.getenv("DISCORD_TOKEN")
ROLE_ID    = int(os.getenv("VERIFIED_ROLE_ID"))
CHANNEL_ID = int(os.getenv("VERIFICATION_CHANNEL_ID"))

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Abonnés par message : {message_id: set(user_id)}
subscribers: dict[int, set[int]] = {}


# ─────────────────────────────────────────────
#  VÉRIFICATION
# ─────────────────────────────────────────────

class VerificationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="✅ Je ne suis pas un robot",
        style=discord.ButtonStyle.green,
        custom_id="verify_button",
    )
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        role = interaction.guild.get_role(ROLE_ID)
        if role is None:
            await interaction.response.send_message(
                "❌ Rôle introuvable. Contacte un administrateur.", ephemeral=True
            )
            return
        if role in interaction.user.roles:
            await interaction.response.send_message("✅ Tu es déjà vérifié(e) !", ephemeral=True)
            return
        await interaction.user.add_roles(role, reason="Vérification par bouton")
        await interaction.response.send_message(
            f"✅ Bienvenue ! Tu as reçu le rôle **{role.name}**.", ephemeral=True
        )


@bot.tree.command(name="setup-verification", description="Envoie le message de vérification dans ce salon.")
@app_commands.checks.has_permissions(administrator=True)
async def setup_verification(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🔐 Vérification",
        description=(
            "Bienvenue sur le serveur !\n\n"
            "Clique sur le bouton ci-dessous pour confirmer que tu n'es pas un robot "
            "et accéder au reste du serveur."
        ),
        color=discord.Color.blurple(),
    )
    embed.set_footer(text="Un seul clic suffit.")
    await interaction.channel.send(embed=embed, view=VerificationView())
    await interaction.response.send_message("✅ Message de vérification envoyé !", ephemeral=True)


@setup_verification.error
async def setup_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    await interaction.response.send_message(
        "❌ Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True
    )


# ─────────────────────────────────────────────
#  SETUP ADMIN VENTE
# ─────────────────────────────────────────────

@bot.tree.command(name="setup-vente", description="Crée le salon admin de gestion des ventes.")
@app_commands.describe(categorie_id="ID de la catégorie admin existante (optionnel)")
@app_commands.checks.has_permissions(administrator=True)
async def setup_vente(interaction: discord.Interaction, categorie_id: str = None):
    guild = interaction.guild

    if categorie_id:
        category = guild.get_channel(int(categorie_id))
        if not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message("❌ ID de catégorie invalide.", ephemeral=True)
            return
    else:
        category = await guild.create_category(
            "━━ ADMINISTRATION ━━",
            overwrites={
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            }
        )

    salon_admin = await guild.create_text_channel(
        "📋・gestion-ventes",
        category=category,
        topic="Utilisez /acc ici pour publier un compte en vente.",
        overwrites={
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
    )

    embed = discord.Embed(
        title="🛒 Gestion des ventes",
        description=(
            "Utilisez la commande ci-dessous pour mettre un compte en vente :\n\n"
            "```/acc name: ... lunar: ... co: ... bin: ... salon: #salon```\n"
            "**Paramètres :**\n"
            "• `name` — Nom du compte\n"
            "• `lunar` — Cosmétiques Lunar (oui / non)\n"
            "• `co` — Current Offer\n"
            "• `bin` — Buy It Now\n"
            "• `salon` — Salon où publier l'annonce\n"
        ),
        color=discord.Color.gold(),
    )
    embed.set_footer(text="Réservé aux administrateurs")
    await salon_admin.send(embed=embed)

    await interaction.response.send_message(
        f"✅ Salon admin créé : {salon_admin.mention}", ephemeral=True
    )


@setup_vente.error
async def setup_vente_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    await interaction.response.send_message(
        "❌ Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True
    )


# ─────────────────────────────────────────────
#  MODAL OFFRE
# ─────────────────────────────────────────────

class OfferModal(discord.ui.Modal, title="💰 Faire une offre"):
    montant = discord.ui.TextInput(
        label="Ton offre",
        placeholder="Ex : 15€",
        required=True,
        max_length=50,
    )

    def __init__(self, salon: discord.TextChannel, message_id: int, account_name: str):
        super().__init__()
        self.salon       = salon
        self.message_id  = message_id
        self.account_name = account_name

    async def on_submit(self, interaction: discord.Interaction):
        # Publier l'offre dans le salon
        embed = discord.Embed(
            title="💰 Nouvelle offre reçue",
            color=discord.Color.gold(),
        )
        embed.add_field(name="🎮  Compte",  value=f"`{self.account_name}`",     inline=True)
        embed.add_field(name="💵  Offre",   value=f"**{self.montant.value}**",  inline=True)
        embed.add_field(name="👤  Acheteur", value=interaction.user.mention,    inline=False)
        await self.salon.send(embed=embed)

        # Notifier les abonnés puis vider la liste
        if self.message_id in subscribers:
            subs = subscribers.pop(self.message_id)
            for user_id in subs:
                if user_id == interaction.user.id:
                    continue
                member = interaction.guild.get_member(user_id)
                if member:
                    try:
                        await member.send(
                            f"🔔 Une offre de **{self.montant.value}** vient d'être faite "
                            f"sur le compte `{self.account_name}` !"
                        )
                    except discord.Forbidden:
                        pass  # DMs fermés

        await interaction.response.send_message(
            f"✅ Offre de **{self.montant.value}** envoyée !", ephemeral=True
        )


# ─────────────────────────────────────────────
#  BOUTONS DYNAMIQUES (persistants après redémarrage)
# ─────────────────────────────────────────────

class OfferButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"offer:(?P<salon_id>[0-9]+):(?P<msg_id>[0-9]+)",
):
    def __init__(self, salon_id: int, msg_id: int):
        super().__init__(
            discord.ui.Button(
                label="💰 Offer",
                style=discord.ButtonStyle.green,
                custom_id=f"offer:{salon_id}:{msg_id}",
            )
        )
        self.salon_id = salon_id
        self.msg_id   = msg_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match,
    ):
        return cls(int(match["salon_id"]), int(match["msg_id"]))

    async def callback(self, interaction: discord.Interaction):
        salon = interaction.guild.get_channel(self.salon_id)
        if salon is None:
            await interaction.response.send_message("❌ Salon introuvable.", ephemeral=True)
            return

        # Lire le nom du compte depuis l'embed du message
        account_name = "Inconnu"
        if interaction.message and interaction.message.embeds:
            for field in interaction.message.embeds[0].fields:
                if "Nom" in field.name:
                    account_name = field.value.strip("`")
                    break

        await interaction.response.send_modal(
            OfferModal(salon=salon, message_id=self.msg_id, account_name=account_name)
        )


class SubscribeButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"subscribe:(?P<msg_id>[0-9]+)",
):
    def __init__(self, msg_id: int):
        super().__init__(
            discord.ui.Button(
                label="🔔 Subscribe",
                style=discord.ButtonStyle.blurple,
                custom_id=f"subscribe:{msg_id}",
            )
        )
        self.msg_id = msg_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match,
    ):
        return cls(int(match["msg_id"]))

    async def callback(self, interaction: discord.Interaction):
        user_id = interaction.user.id

        if self.msg_id not in subscribers:
            subscribers[self.msg_id] = set()

        if user_id in subscribers[self.msg_id]:
            subscribers[self.msg_id].discard(user_id)
            await interaction.response.send_message(
                "🔕 Tu ne recevras plus de notification pour cette annonce.", ephemeral=True
            )
        else:
            subscribers[self.msg_id].add(user_id)
            await interaction.response.send_message(
                "🔔 Tu seras notifié(e) en DM lors d'une offre. Clique à nouveau pour te désabonner.",
                ephemeral=True,
            )


class SaleView(discord.ui.View):
    """Vue attachée à une annonce (boutons Offer + Subscribe)."""
    def __init__(self, salon_id: int, msg_id: int):
        super().__init__(timeout=None)
        self.add_item(OfferButton(salon_id, msg_id))
        self.add_item(SubscribeButton(msg_id))


# ─────────────────────────────────────────────
#  COMMANDE /acc
# ─────────────────────────────────────────────

@bot.tree.command(name="acc", description="Publie un compte en vente (admin).")
@app_commands.describe(
    name="Nom / pseudo du compte",
    lunar="Cosmétiques Lunar Client ? (oui / non)",
    co="Current Offer — offre actuelle (ex: 10€ ou Aucune)",
    bin="Buy It Now — prix fixe (ex: 25€)",
    salon="Salon où publier l'annonce et recevoir les offres",
)
@app_commands.checks.has_permissions(administrator=True)
async def acc(
    interaction: discord.Interaction,
    name: str,
    lunar: str,
    co: str,
    bin: str,
    salon: discord.TextChannel,
):
    lunar_display = "✅ Oui" if lunar.lower() in ("oui", "yes", "o") else "❌ Non"

    embed = discord.Embed(
        title=f"🎮  {name}",
        description="Un nouveau compte est disponible à la vente !",
        color=discord.Color.green(),
    )
    embed.add_field(name="👤  Nom du compte",       value=f"`{name}`",       inline=True)
    embed.add_field(name="🌙  Cosmétiques Lunar",   value=lunar_display,     inline=True)
    embed.add_field(name="​",                        value="​",               inline=False)
    embed.add_field(name="💬  Current Offer (C/O)", value=f"`{co}`",         inline=True)
    embed.add_field(name="💰  Buy It Now (BIN)",    value=f"**{bin}**",      inline=True)
    embed.add_field(
        name="📩  Comment acheter ?",
        value="Clique sur **Offer** pour faire une offre, ou **Subscribe** pour être notifié(e) lors d'une offre.",
        inline=False,
    )
    embed.set_footer(text="Offre valable jusqu'à la vente du compte.")

    # 1. Envoyer l'embed sans boutons pour obtenir le message_id
    msg = await salon.send(embed=embed)

    # 2. Rattacher les boutons avec le vrai message_id
    await msg.edit(view=SaleView(salon_id=salon.id, msg_id=msg.id))

    await interaction.response.send_message(
        f"✅ Annonce publiée dans {salon.mention}", ephemeral=True
    )


@acc.error
async def acc_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    await interaction.response.send_message(
        "❌ Permissions insuffisantes ou paramètre invalide.", ephemeral=True
    )


# ─────────────────────────────────────────────
#  DÉMARRAGE
# ─────────────────────────────────────────────

@bot.event
async def on_ready():
    bot.add_view(VerificationView())
    bot.add_dynamic_items(OfferButton, SubscribeButton)  # boutons persistants après redémarrage
    await bot.tree.sync()
    print(f"✅ Bot connecté : {bot.user} (ID: {bot.user.id})")


bot.run(TOKEN)
