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
                "❌ Erreur : rôle introuvable. Contacte un administrateur.",
                ephemeral=True,
            )
            return

        if role in interaction.user.roles:
            await interaction.response.send_message(
                "✅ Tu es déjà vérifié(e) !",
                ephemeral=True,
            )
            return

        await interaction.user.add_roles(role, reason="Vérification par bouton")
        await interaction.response.send_message(
            f"✅ Bienvenue ! Tu as reçu le rôle **{role.name}**.",
            ephemeral=True,
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

@bot.tree.command(
    name="setup-vente",
    description="Crée le salon admin de gestion des ventes dans une catégorie admin."
)
@app_commands.describe(categorie_id="ID de la catégorie admin existante (optionnel)")
@app_commands.checks.has_permissions(administrator=True)
async def setup_vente(interaction: discord.Interaction, categorie_id: str = None):
    guild = interaction.guild

    # Récupère ou crée la catégorie admin
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

    # Crée le salon admin de vente
    salon_admin = await guild.create_text_channel(
        "📋・gestion-ventes",
        category=category,
        topic="Utilisez /creer-compte ici pour publier un compte en vente.",
        overwrites={
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
    )

    embed = discord.Embed(
        title="🛒 Gestion des ventes",
        description=(
            "Utilisez la commande ci-dessous dans ce salon pour mettre un compte en vente :\n\n"
            "```/creer-compte name: ... lunar: ... co: ... bin: ...```\n"
            "**Paramètres :**\n"
            "• `name` — Nom / pseudo du compte\n"
            "• `lunar` — Cosmétiques Lunar (oui / non)\n"
            "• `co` — Current Offer (offre actuelle)\n"
            "• `bin` — Buy It Now (prix fixe)\n\n"
            "Le bot créera automatiquement un salon dédié et publiera l'annonce."
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
#  CRÉER UNE ANNONCE DE VENTE DE COMPTE
# ─────────────────────────────────────────────

@bot.tree.command(
    name="creer-compte",
    description="Publie un compte en vente (admin seulement)."
)
@app_commands.describe(
    name="Nom / pseudo du compte",
    lunar="Cosmétiques Lunar Client ? (oui / non)",
    co="Current Offer — offre actuelle (ex: 10€ ou Aucune)",
    bin="Buy It Now — prix fixe (ex: 25€)",
    salon_public="Salon public où publier l'annonce",
    categorie_ventes_id="ID de la catégorie où créer le salon de vente (optionnel)",
)
@app_commands.checks.has_permissions(administrator=True)
async def creer_compte(
    interaction: discord.Interaction,
    name: str,
    lunar: str,
    co: str,
    bin: str,
    salon_public: discord.TextChannel,
    categorie_ventes_id: str = None,
):
    guild = interaction.guild

    lunar_display = "✅ Oui" if lunar.lower() in ("oui", "yes", "o") else "❌ Non"

    # ── Catégorie des ventes ──
    if categorie_ventes_id:
        cat_ventes = guild.get_channel(int(categorie_ventes_id))
    else:
        cat_ventes = discord.utils.get(guild.categories, name="━━ VENTES ━━")
        if cat_ventes is None:
            cat_ventes = await guild.create_category(
                "━━ VENTES ━━",
                overwrites={
                    guild.default_role: discord.PermissionOverwrite(view_channel=True, send_messages=False),
                    guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                }
            )

    # ── Salon dédié à ce compte ──
    nom_salon = f"compte・{name.lower().replace(' ', '-')}"
    salon_vente = await guild.create_text_channel(
        nom_salon,
        category=cat_ventes,
        topic=f"Vente du compte {name} | BIN : {bin}",
        overwrites={
            guild.default_role: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
    )

    # ── Embed annonce ──
    embed_annonce = discord.Embed(
        title=f"🎮  {name}",
        description="Un nouveau compte est disponible à la vente !",
        color=discord.Color.green(),
    )
    embed_annonce.add_field(name="👤  Nom du compte", value=f"`{name}`", inline=True)
    embed_annonce.add_field(name="🌙  Cosmétiques Lunar", value=lunar_display, inline=True)
    embed_annonce.add_field(name="​", value="​", inline=False)
    embed_annonce.add_field(name="💬  Current Offer (C/O)", value=f"`{co}`", inline=True)
    embed_annonce.add_field(name="💰  Buy It Now (BIN)", value=f"**{bin}**", inline=True)
    embed_annonce.add_field(
        name="📩  Intéressé(e) ?",
        value=f"Rendez-vous dans {salon_vente.mention} pour faire une offre.",
        inline=False,
    )
    embed_annonce.set_footer(text="Offre valable jusqu'à la vente du compte.")

    # ── Message dans le salon dédié ──
    embed_salon = discord.Embed(
        title=f"📋  Détails — {name}",
        color=discord.Color.blurple(),
    )
    embed_salon.add_field(name="👤  Nom", value=f"`{name}`", inline=True)
    embed_salon.add_field(name="🌙  Lunar Cosmetics", value=lunar_display, inline=True)
    embed_salon.add_field(name="​", value="​", inline=False)
    embed_salon.add_field(name="💬  C/O", value=f"`{co}`", inline=True)
    embed_salon.add_field(name="💰  BIN", value=f"**{bin}**", inline=True)
    embed_salon.add_field(
        name="📌  Instructions",
        value="Postez votre offre ici. Le vendeur vous contactera en DM.",
        inline=False,
    )

    await salon_vente.send(embed=embed_salon)
    await salon_public.send(embed=embed_annonce)

    await interaction.response.send_message(
        f"✅ Annonce publiée dans {salon_public.mention} — salon dédié : {salon_vente.mention}",
        ephemeral=True,
    )


@creer_compte.error
async def creer_compte_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    await interaction.response.send_message(
        "❌ Tu n'as pas la permission ou un paramètre est invalide.", ephemeral=True
    )


# ─────────────────────────────────────────────
#  DÉMARRAGE
# ─────────────────────────────────────────────

@bot.event
async def on_ready():
    bot.add_view(VerificationView())
    await bot.tree.sync()
    print(f"✅ Bot connecté : {bot.user} (ID: {bot.user.id})")


bot.run(TOKEN)
