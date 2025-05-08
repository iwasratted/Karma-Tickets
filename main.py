import discord
from discord.ext import commands
from discord import app_commands
import os
import asyncio
from keep_alive import keep_alive
import pymongo
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TOKEN")
MONGO_URL = os.getenv("MONGO_URL")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="$", intents=intents)
bot.remove_command("help")

client = pymongo.MongoClient(MONGO_URL)
db = client["karma_ticket"]
config_col = db["configs"]

# Sync slash commands
@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"❌ Sync error: {e}")
    print(f"Bot logged in as {bot.user}")

# /setup command
@bot.tree.command(name="setup", description="Set up ticket system")
async def setup(interaction: discord.Interaction):
    guild = interaction.guild
    role = await guild.create_role(name="Ticket Staff")
    await interaction.response.send_message(f"✅ Created role: {role.mention}", ephemeral=True)

# /panel command
@bot.tree.command(name="panel", description="Build the ticket panel embed")
async def panel(interaction: discord.Interaction):
    def check(m):
        return m.author == interaction.user and m.channel == interaction.channel

    await interaction.response.send_message("Author name?", ephemeral=True)
    author = (await bot.wait_for('message', check=check, timeout=60)).content

    await interaction.followup.send("Title?", ephemeral=True)
    title = (await bot.wait_for('message', check=check, timeout=60)).content

    await interaction.followup.send("Description?", ephemeral=True)
    desc = (await bot.wait_for('message', check=check, timeout=60)).content

    await interaction.followup.send("Image URL? (or type 'none')", ephemeral=True)
    image_url = (await bot.wait_for('message', check=check, timeout=60)).content

    embed = discord.Embed(title=title, description=desc, color=discord.Color.blurple())
    embed.set_author(name=author)
    if image_url.lower() != "none":
        embed.set_image(url=image_url)

    msg = await interaction.channel.send(embed=embed)
    await interaction.followup.send(f"✅ Embed sent. Message ID: `{msg.id}`", ephemeral=True)

# /button command
@bot.tree.command(name="button", description="Add a ticket button to a message")
@app_commands.describe(name="Name of button", category_id="Category where ticket goes", message_id="Message to attach button")
async def button(interaction: discord.Interaction, name: str, category_id: str, message_id: str):
    category = discord.utils.get(interaction.guild.categories, id=int(category_id))
    if not category:
        await interaction.response.send_message("❌ Invalid category ID", ephemeral=True)
        return

    view = discord.ui.View()

    async def create_ticket_callback(inter):
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            inter.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }

        staff_role = discord.utils.get(inter.guild.roles, name="Ticket Staff")
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True)

        channel = await category.create_text_channel(name=f"{name}-{inter.user.name}", overwrites=overwrites)
        await channel.send(f"🎫 Ticket created by {inter.user.mention}")

        await inter.response.send_message(f"✅ Ticket created: {channel.mention}", ephemeral=True)

    button = discord.ui.Button(label=name, style=discord.ButtonStyle.green)

    async def button_callback(interaction: discord.Interaction):
        await create_ticket_callback(interaction)

    button.callback = button_callback
    view.add_item(button)

    try:
        msg = await interaction.channel.fetch_message(int(message_id))
        await msg.edit(view=view)
        await interaction.response.send_message("✅ Button added", ephemeral=True)
    except:
        await interaction.response.send_message("❌ Failed to find message", ephemeral=True)

# $add command
@bot.command()
async def add(ctx, member: discord.Member):
    if ctx.channel.category and "ticket" in ctx.channel.name:
        await ctx.channel.set_permissions(member, view_channel=True, send_messages=True)
        await ctx.send(f"✅ Added {member.mention} to the ticket.")
    else:
        await ctx.send("❌ This isn't a ticket channel.")

# $rename command
@bot.command()
async def rename(ctx, *, new_name):
    await ctx.channel.edit(name=new_name)
    await ctx.send(f"✅ Renamed channel to `{new_name}`.")

# $unclaim command
@bot.command()
async def unclaim(ctx):
    await ctx.send("Unclaimed. (You can implement role removal logic here.)")

# Buttons: Claim, Close, Close w/ Reason
class TicketControls(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

        self.add_item(discord.ui.Button(label="Claim", style=discord.ButtonStyle.primary, custom_id="claim"))
        self.add_item(discord.ui.Button(label="Close", style=discord.ButtonStyle.danger, custom_id="close"))
        self.add_item(discord.ui.Button(label="Close with Reason", style=discord.ButtonStyle.secondary, custom_id="close_reason"))

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.primary, custom_id="claim")
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"{interaction.user.mention} claimed this ticket.", ephemeral=False)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, custom_id="close")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.channel.delete()

    @discord.ui.button(label="Close with Reason", style=discord.ButtonStyle.secondary, custom_id="close_reason")
    async def close_reason_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Reason?", ephemeral=True)
        try:
            msg = await bot.wait_for("message", timeout=30.0, check=lambda m: m.author == interaction.user)
            await interaction.channel.send(f"Ticket closed: {msg.content}")
            await interaction.channel.delete()
        except asyncio.TimeoutError:
            await interaction.followup.send("❌ Timed out.", ephemeral=True)

# You can use this view anywhere ticket is created:
# await channel.send("🎟️ Controls", view=TicketControls())

keep_alive()
bot.run(TOKEN)
