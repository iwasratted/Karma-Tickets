import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button, Modal, TextInput
import os
from keep_alive import keep_alive
from pymongo import MongoClient
from dotenv import load_dotenv
import requests

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
GUILD_ID = int(os.getenv("GUILD_ID"))

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="$", intents=intents)
tree = bot.tree
cluster = MongoClient(MONGO_URI)
db = cluster["karma_ticket"]
config_col = db["config"]

class TicketControls(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(Button(label="Claim", style=discord.ButtonStyle.primary, custom_id="claim"))
        self.add_item(Button(label="Close", style=discord.ButtonStyle.danger, custom_id="close"))
        self.add_item(Button(label="Close w/ Reason", style=discord.ButtonStyle.secondary, custom_id="close_reason"))

@bot.event
async def on_ready():
    await tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"Logged in as {bot.user}")

@tree.command(name="setup", description="Setup the ticket bot", guild=discord.Object(id=GUILD_ID))
async def setup(interaction: discord.Interaction):
    guild = interaction.guild
    role = await guild.create_role(name="Ticket Staff")
    config_col.update_one({"guild_id": guild.id}, {"$set": {"staff_role": role.id}}, upsert=True)
    await interaction.response.send_message(f"✅ Setup complete. Created role {role.mention}", ephemeral=True)

class EmbedModal(Modal, title="Create Ticket Panel Embed"):
    author = TextInput(label="Author", required=False)
    title_field = TextInput(label="Title")
    description = TextInput(label="Description")
    image_url = TextInput(label="Image URL", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(title=self.title_field.value, description=self.description.value, color=discord.Color.blue())
        if self.author.value:
            embed.set_author(name=self.author.value)
        if self.image_url.value:
            embed.set_image(url=self.image_url.value)
        msg = await interaction.channel.send(embed=embed)
        config_col.update_one({"guild_id": interaction.guild.id}, {"$set": {"panel_message": msg.id}}, upsert=True)
        await interaction.response.send_message("✅ Embed created and sent.", ephemeral=True)

@tree.command(name="panel", description="Create a ticket panel", guild=discord.Object(id=GUILD_ID))
async def panel(interaction: discord.Interaction):
    await interaction.response.send_modal(EmbedModal())

@tree.command(name="button", description="Add a button to the panel", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(name="Button label", category_id="Target category ID")
async def button(interaction: discord.Interaction, name: str, category_id: str):
    data = config_col.find_one({"guild_id": interaction.guild.id})
    msg_id = data.get("panel_message")
    category = interaction.guild.get_channel(int(category_id))
    if not category:
        return await interaction.response.send_message("❌ Invalid category ID.", ephemeral=True)

    class TicketButton(Button):
        def __init__(self):
            super().__init__(label=name, style=discord.ButtonStyle.success, custom_id=f"ticket_{name}")

        async def callback(self, inter: discord.Interaction):
            staff_role_id = config_col.find_one({"guild_id": interaction.guild.id}).get("staff_role")
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                inter.user: discord.PermissionOverwrite(view_channel=True, send_messages=True)
            }
            if staff_role_id:
                role = interaction.guild.get_role(staff_role_id)
                overwrites[role] = discord.PermissionOverwrite(view_channel=True)

            channel = await category.create_text_channel(f"{name}-{inter.user.name}", overwrites=overwrites)
            embed = discord.Embed(title="🎫 Ticket Opened", description=f"Hey {inter.user.mention} 👋\nA staff member will assist you shortly.", color=discord.Color.green())
            await channel.send(embed=embed, view=TicketControls())
            await inter.response.send_message(f"✅ Ticket created: {channel.mention}", ephemeral=True)

            # Log the ticket creation to webhook if set
            log_channel = config_col.find_one({"guild_id": interaction.guild.id}).get("log_channel")
            if log_channel:
                webhook_url = config_col.find_one({"guild_id": interaction.guild.id}).get("webhook_url")
                if webhook_url:
                    log_data = {
                        "content": f"Ticket created by {inter.user.mention} in category {category.name}.",
                        "embeds": [{
                            "title": "New Ticket Opened",
                            "description": f"Ticket channel: {channel.mention}\nCategory: {category.name}",
                            "color": 3066993
                        }]
                    }
                    requests.post(webhook_url, json=log_data)

    view = View()
    view.add_item(TicketButton())
    channel = interaction.channel
    try:
        msg = await channel.fetch_message(msg_id)
        await msg.edit(view=view)
        await interaction.response.send_message("✅ Button added to panel.", ephemeral=True)
    except:
        await interaction.response.send_message("❌ Failed to find panel message.", ephemeral=True)

@tree.command(name="setlogchannel", description="Set the log channel for ticket actions", guild=discord.Object(id=GUILD_ID))
async def set_log_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    config_col.update_one({"guild_id": interaction.guild.id}, {"$set": {"log_channel": channel.id}}, upsert=True)
    await interaction.response.send_message(f"✅ Log channel set to {channel.mention}", ephemeral=True)

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component:
        cid = interaction.data["custom_id"]
        if cid == "claim":
            await interaction.response.send_message(f"✅ Claimed by {interaction.user.mention}.", ephemeral=False)

            # Log claim action
            log_channel = config_col.find_one({"guild_id": interaction.guild.id}).get("log_channel")
            if log_channel:
                webhook_url = config_col.find_one({"guild_id": interaction.guild.id}).get("webhook_url")
                if webhook_url:
                    log_data = {
                        "content": f"Ticket claimed by {interaction.user.mention}.",
                        "embeds": [{
                            "title": "Ticket Claimed",
                            "description": f"Claimed by {interaction.user.mention}",
                            "color": 3066993
                        }]
                    }
                    requests.post(webhook_url, json=log_data)
        elif cid == "close":
            await interaction.channel.delete()

            # Log close action
            log_channel = config_col.find_one({"guild_id": interaction.guild.id}).get("log_channel")
            if log_channel:
                webhook_url = config_col.find_one({"guild_id": interaction.guild.id}).get("webhook_url")
                if webhook_url:
                    log_data = {
                        "content": f"Ticket closed by {interaction.user.mention}.",
                        "embeds": [{
                            "title": "Ticket Closed",
                            "description": f"Closed by {interaction.user.mention}",
                            "color": 15158332
                        }]
                    }
                    requests.post(webhook_url, json=log_data)
        elif cid == "close_reason":
            await interaction.response.send_modal(ReasonModal())

    await bot.process_application_commands(interaction)

class ReasonModal(Modal, title="Close with Reason"):
    reason = TextInput(label="Reason", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.channel.send(f"Ticket closed by {interaction.user.mention} with reason: {self.reason.value}")
        await interaction.channel.delete()

keep_alive()
bot.run(TOKEN)
