import discord
from discord.ext import commands
from discord import app_commands
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
ROLE_ID = int(os.getenv("VERIFIED_ROLE_ID"))
CHANNEL_ID = int(os.getenv("VERIFICATION_CHANNEL_ID"))

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


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


@bot.event
async def on_ready():
    bot.add_view(VerificationView())  # Restaure le bouton après redémarrage
    await bot.tree.sync()
    print(f"Bot connecté en tant que {bot.user} (ID: {bot.user.id})")


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
        "❌ Tu n'as pas la permission d'utiliser cette commande.",
        ephemeral=True,
    )


bot.run(TOKEN)
