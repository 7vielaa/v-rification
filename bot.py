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
intents.members   = True
intents.presences = True  # Required to track online/offline status

bot = commands.Bot(command_prefix="!", intents=intents)

# Subscribers per message: {message_id: set(user_id)}
subscribers: dict[int, set[int]] = {}


# ─────────────────────────────────────────────
#  VERIFICATION
# ─────────────────────────────────────────────

class VerificationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="✅ I am not a robot",
        style=discord.ButtonStyle.green,
        custom_id="verify_button",
    )
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        role = interaction.guild.get_role(ROLE_ID)
        if role is None:
            await interaction.response.send_message(
                "❌ Role not found. Please contact an administrator.", ephemeral=True
            )
            return
        if role in interaction.user.roles:
            await interaction.response.send_message("✅ You are already verified!", ephemeral=True)
            return
        await interaction.user.add_roles(role, reason="Verification button")
        await interaction.response.send_message(
            f"✅ Welcome! You have been given the **{role.name}** role.", ephemeral=True
        )


@bot.tree.command(name="setup-verification", description="Send the verification message in this channel.")
@app_commands.checks.has_permissions(administrator=True)
async def setup_verification(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🔐 Verification",
        description=(
            "Welcome to the server!\n\n"
            "Click the button below to confirm that you are not a robot "
            "and gain access to the rest of the server."
        ),
        color=discord.Color.blurple(),
    )
    embed.set_footer(text="One click is all it takes.")
    await interaction.channel.send(embed=embed, view=VerificationView())
    await interaction.response.send_message("✅ Verification message sent!", ephemeral=True)


@setup_verification.error
async def setup_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    await interaction.response.send_message(
        "❌ You do not have permission to use this command.", ephemeral=True
    )


# ─────────────────────────────────────────────
#  SALES ADMIN SETUP
# ─────────────────────────────────────────────

@bot.tree.command(name="setup-sales", description="Create the admin sales management channel.")
@app_commands.describe(category_id="ID of an existing admin category (optional)")
@app_commands.checks.has_permissions(administrator=True)
async def setup_sales(interaction: discord.Interaction, category_id: str = None):
    guild = interaction.guild

    if category_id:
        category = guild.get_channel(int(category_id))
        if not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message("❌ Invalid category ID.", ephemeral=True)
            return
    else:
        category = await guild.create_category(
            "━━ ADMINISTRATION ━━",
            overwrites={
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            }
        )

    admin_channel = await guild.create_text_channel(
        "📋・sales-management",
        category=category,
        topic="Use /acc here to list an account for sale.",
        overwrites={
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
    )

    embed = discord.Embed(
        title="🛒 Sales Management",
        description=(
            "Use the command below to list an account for sale:\n\n"
            "```/acc name: ... lunar: ... co: ... bin: ... channel: #channel```\n"
            "**Parameters:**\n"
            "• `name` — Account name\n"
            "• `lunar` — Lunar cosmetics (yes / no)\n"
            "• `co` — Current Offer\n"
            "• `bin` — Buy It Now\n"
            "• `channel` — Channel where the listing will be posted\n"
        ),
        color=discord.Color.gold(),
    )
    embed.set_footer(text="Restricted to administrators.")
    await admin_channel.send(embed=embed)

    await interaction.response.send_message(
        f"✅ Admin channel created: {admin_channel.mention}", ephemeral=True
    )


@setup_sales.error
async def setup_sales_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    await interaction.response.send_message(
        "❌ You do not have permission to use this command.", ephemeral=True
    )


# ─────────────────────────────────────────────
#  OFFER MODAL
# ─────────────────────────────────────────────

class OfferModal(discord.ui.Modal, title="💰 Place an Offer"):
    amount = discord.ui.TextInput(
        label="Your offer",
        placeholder="e.g. $15",
        required=True,
        max_length=50,
    )

    def __init__(self, channel: discord.TextChannel, message_id: int, account_name: str):
        super().__init__()
        self.channel      = channel
        self.message_id   = message_id
        self.account_name = account_name

    async def on_submit(self, interaction: discord.Interaction):
        # Post the offer in the channel
        embed = discord.Embed(
            title="💰 New Offer Received",
            color=discord.Color.gold(),
        )
        embed.add_field(name="🎮  Account", value=f"`{self.account_name}`",    inline=True)
        embed.add_field(name="💵  Offer",   value=f"**{self.amount.value}**",  inline=True)
        embed.add_field(name="👤  Buyer",   value=interaction.user.mention,    inline=False)
        await self.channel.send(embed=embed)

        # Notify all subscribers then clear the list
        if self.message_id in subscribers:
            subs = subscribers.pop(self.message_id)
            for user_id in subs:
                if user_id == interaction.user.id:
                    continue
                member = interaction.guild.get_member(user_id)
                if member:
                    try:
                        await member.send(
                            f"🔔 An offer of **{self.amount.value}** was just placed "
                            f"on the account `{self.account_name}`!"
                        )
                    except discord.Forbidden:
                        pass  # DMs closed

        await interaction.response.send_message(
            f"✅ Offer of **{self.amount.value}** submitted!", ephemeral=True
        )


# ─────────────────────────────────────────────
#  DYNAMIC BUTTONS (persistent across restarts)
# ─────────────────────────────────────────────

class OfferButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"offer:(?P<channel_id>[0-9]+):(?P<msg_id>[0-9]+)",
):
    def __init__(self, channel_id: int, msg_id: int):
        super().__init__(
            discord.ui.Button(
                label="💰 Offer",
                style=discord.ButtonStyle.green,
                custom_id=f"offer:{channel_id}:{msg_id}",
            )
        )
        self.channel_id = channel_id
        self.msg_id     = msg_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match,
    ):
        return cls(int(match["channel_id"]), int(match["msg_id"]))

    async def callback(self, interaction: discord.Interaction):
        channel = interaction.guild.get_channel(self.channel_id)
        if channel is None:
            await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
            return

        # Read the account name from the embed
        account_name = "Unknown"
        if interaction.message and interaction.message.embeds:
            for field in interaction.message.embeds[0].fields:
                if "Account" in field.name:
                    account_name = field.value.strip("`")
                    break

        await interaction.response.send_modal(
            OfferModal(channel=channel, message_id=self.msg_id, account_name=account_name)
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
                "🔕 You will no longer receive notifications for this listing.", ephemeral=True
            )
        else:
            subscribers[self.msg_id].add(user_id)
            await interaction.response.send_message(
                "🔔 You will be notified by DM when an offer is placed. Click again to unsubscribe.",
                ephemeral=True,
            )


class SaleView(discord.ui.View):
    """View attached to a sale listing (Offer + Subscribe buttons)."""
    def __init__(self, channel_id: int, msg_id: int):
        super().__init__(timeout=None)
        self.add_item(OfferButton(channel_id, msg_id))
        self.add_item(SubscribeButton(msg_id))


# ─────────────────────────────────────────────
#  /acc COMMAND
# ─────────────────────────────────────────────

@bot.tree.command(name="acc", description="List an account for sale (admin only).")
@app_commands.describe(
    name="Account name / username",
    lunar="Lunar Client cosmetics? (yes / no)",
    co="Current Offer — current highest offer (e.g. $10 or None)",
    bin="Buy It Now — fixed price (e.g. $25)",
    channel="Channel where the listing will be posted and offers received",
)
@app_commands.checks.has_permissions(administrator=True)
async def acc(
    interaction: discord.Interaction,
    name: str,
    lunar: str,
    co: str,
    bin: str,
    channel: discord.TextChannel,
):
    lunar_display = "✅ Yes" if lunar.lower() in ("yes", "oui", "y", "o") else "❌ No"

    embed = discord.Embed(
        title=f"🎮  {name}",
        description="A new account is available for sale!",
        color=discord.Color.green(),
    )
    embed.add_field(name="👤  Account Name",        value=f"`{name}`",       inline=True)
    embed.add_field(name="🌙  Lunar Cosmetics",     value=lunar_display,     inline=True)
    embed.add_field(name="​",                        value="​",               inline=False)
    embed.add_field(name="💬  Current Offer (C/O)", value=f"`{co}`",         inline=True)
    embed.add_field(name="💰  Buy It Now (BIN)",    value=f"**{bin}**",      inline=True)
    embed.add_field(
        name="📩  Interested?",
        value="Click **Offer** to place a bid, or **Subscribe** to get notified when an offer is made.",
        inline=False,
    )
    embed.set_footer(text="Listing valid until the account is sold.")

    # 1. Send embed without buttons to get the message ID
    msg = await channel.send(embed=embed)

    # 2. Attach buttons with the real message ID
    await msg.edit(view=SaleView(channel_id=channel.id, msg_id=msg.id))

    await interaction.response.send_message(
        f"✅ Listing posted in {channel.mention}", ephemeral=True
    )


@acc.error
async def acc_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    await interaction.response.send_message(
        "❌ Insufficient permissions or invalid parameter.", ephemeral=True
    )


# ─────────────────────────────────────────────
#  VISIBILITY — HIDE OFFLINE MEMBERS
# ─────────────────────────────────────────────

ONLINE_ROLE_NAME = "o"


def is_online(status: discord.Status) -> bool:
    return status not in (discord.Status.offline, discord.Status.invisible)


async def get_or_create_online_role(guild: discord.Guild) -> discord.Role:
    """Return the Online role, creating it if it doesn't exist."""
    role = discord.utils.get(guild.roles, name=ONLINE_ROLE_NAME)
    if role is None:
        role = await guild.create_role(
            name=ONLINE_ROLE_NAME,
            color=discord.Color.green(),
            reason="Auto-created for online visibility system",
        )
    return role


@bot.tree.command(
    name="setup-visibility",
    description="Hide offline members from all channels (admins always see everyone).",
)
@app_commands.checks.has_permissions(administrator=True)
async def setup_visibility(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    online_role = await get_or_create_online_role(guild)
    admin_role  = discord.utils.get(guild.roles, permissions=discord.Permissions(administrator=True))

    updated = 0
    for channel in guild.channels:
        # Skip the channel used for this command
        if channel == interaction.channel:
            continue
        try:
            overwrites = dict(channel.overwrites)

            # Default role (@everyone): cannot view the channel
            overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=False)

            # Online role: can view
            overwrites[online_role] = discord.PermissionOverwrite(view_channel=True)

            # Bot itself: always has access
            overwrites[guild.me] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

            await channel.edit(overwrites=overwrites, reason="Visibility setup: hide offline members")
            updated += 1
        except discord.Forbidden:
            pass

    # Give the Online role to all currently online members
    synced = 0
    for member in guild.members:
        if member.bot or member.guild_permissions.administrator:
            continue
        if is_online(member.status) and online_role not in member.roles:
            await member.add_roles(online_role, reason="Visibility sync on setup")
            synced += 1
        elif not is_online(member.status) and online_role in member.roles:
            await member.remove_roles(online_role, reason="Visibility sync on setup")

    await interaction.followup.send(
        f"✅ Visibility configured!\n"
        f"• **{updated}** channels updated\n"
        f"• **{synced}** members synced\n\n"
        f"Offline members are now hidden from all channels. Administrators can always see everyone.",
        ephemeral=True,
    )


@setup_visibility.error
async def setup_visibility_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    await interaction.response.send_message(
        "❌ You do not have permission to use this command.", ephemeral=True
    )


@bot.event
async def on_presence_update(before: discord.Member, after: discord.Member):
    """Add/remove the Online role when a member's status changes."""
    # Skip bots and admins (admins always see everything via their permissions)
    if after.bot or after.guild_permissions.administrator:
        return

    online_role = discord.utils.get(after.guild.roles, name=ONLINE_ROLE_NAME)
    if online_role is None:
        return  # Visibility system not set up yet

    was_online = is_online(before.status)
    now_online  = is_online(after.status)

    if not was_online and now_online:
        # Member came online → give role
        if online_role not in after.roles:
            await after.add_roles(online_role, reason="Member came online")

    elif was_online and not now_online:
        # Member went offline → remove role
        if online_role in after.roles:
            await after.remove_roles(online_role, reason="Member went offline")


@bot.event
async def on_member_join(member: discord.Member):
    """Give the Online role immediately if the new member is online."""
    if member.bot or member.guild_permissions.administrator:
        return
    online_role = discord.utils.get(member.guild.roles, name=ONLINE_ROLE_NAME)
    if online_role and is_online(member.status):
        await member.add_roles(online_role, reason="New member joined online")


# ─────────────────────────────────────────────
#  STARTUP
# ─────────────────────────────────────────────

@bot.event
async def on_ready():
    bot.add_view(VerificationView())
    bot.add_dynamic_items(OfferButton, SubscribeButton)  # restore buttons after restart
    await bot.tree.sync()
    print(f"✅ Bot connected as {bot.user} (ID: {bot.user.id})")


bot.run(TOKEN)
