import discord
from discord.ext import commands
from discord import app_commands, Interaction, Embed, ButtonStyle, TextStyle
from discord.ui import View, Button, Modal, TextInput
from pymongo import MongoClient
from dotenv import load_dotenv
from flask import Flask
from keep_alive import keep_alive
import threading
import os

load_dotenv()

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="$", intents=intents)
TOKEN = os.getenv("TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["karma_ticket"]
config = db["config"]

# Keep-alive webserver
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

threading.Thread(target=run).start()

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Logged in as {bot.user}")

@bot.hybrid_command(name="setup")
async def setup(ctx):
    guild = ctx.guild
    role = await guild.create_role(name="Ticket Staff")
    await ctx.reply(f"✅ Created role: {role.mention}")

@bot.hybrid_command(name="logchannel")
async def logchannel(ctx, channel: discord.TextChannel):
    config.update_one({"_id": ctx.guild.id}, {"$set": {"log_channel": channel.id}}, upsert=True)
    await ctx.reply(f"✅ Log channel set to {channel.mention}")

@bot.hybrid_command(name="panel")
async def panel(ctx, title: str, description: str):
    embed = Embed(title=title, description=description, color=discord.Color.blurple())
    msg = await ctx.channel.send(embed=embed)
    config.update_one({"_id": ctx.guild.id}, {"$set": {"panel_msg": msg.id}}, upsert=True)
    await ctx.reply("✅ Ticket panel created!")

@bot.hybrid_command(name="button")
async def button(ctx, name: str, category_id: str, message_id: str):
    category_id = int(category_id)
    message_id = int(message_id)
    msg = await ctx.channel.fetch_message(message_id)
    view = View(timeout=None)
    view.add_item(Button(label=name, style=ButtonStyle.primary, custom_id=f"ticket_{name}_{category_id}"))
    await msg.edit(view=view)
    await ctx.reply("✅ Button added to the panel.")

class CloseReasonModal(Modal, title="Close Ticket With Reason"):
    reason = TextInput(label="Reason", style=TextStyle.paragraph)

    async def on_submit(self, interaction: Interaction):
        await interaction.channel.delete()
        log_data = config.find_one({"_id": interaction.guild.id})
        if log_data and "log_channel" in log_data:
            log_channel = interaction.guild.get_channel(log_data["log_channel"])
            if log_channel:
                await log_channel.send(f"📝 Ticket closed with reason: {self.reason.value}")

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component:
        cid = interaction.data['custom_id']

        if cid.startswith("ticket_"):
            _, name, category_id = cid.split("_")
            category = interaction.guild.get_channel(int(category_id))
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            staff_role = discord.utils.get(interaction.guild.roles, name="Ticket Staff")
            if staff_role:
                overwrites[staff_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

            ticket_channel = await interaction.guild.create_text_channel(
                f"{name}-ticket-{interaction.user.name}",
                category=category,
                overwrites=overwrites,
                topic=f"Ticket by {interaction.user.name}"
            )

            view = View()
            view.add_item(Button(label="🔒 Close", style=ButtonStyle.danger, custom_id="close_now"))
            view.add_item(Button(label="📝 Close with Reason", style=ButtonStyle.secondary, custom_id="close_reason"))

            await ticket_channel.send(f"🎫 Ticket created for {interaction.user.mention}", view=view)
            await interaction.response.send_message(f"🎫 Ticket created: {ticket_channel.mention}", ephemeral=True)

        elif cid == "close_now":
            await interaction.channel.delete()
            log_data = config.find_one({"_id": interaction.guild.id})
            if log_data and "log_channel" in log_data:
                log_channel = interaction.guild.get_channel(log_data["log_channel"])
                if log_channel:
                    await log_channel.send(f"🔒 Ticket closed by {interaction.user.mention}")

        elif cid == "close_reason":
            await interaction.response.send_modal(CloseReasonModal())

@bot.hybrid_command(name="rename")
async def rename(ctx, new_name: str):
    await ctx.channel.edit(name=new_name)
    await ctx.reply(f"✅ Channel renamed to {new_name}")

@bot.hybrid_command(name="add")
async def add(ctx, user: discord.User):
    await ctx.channel.set_permissions(user, read_messages=True, send_messages=True)
    await ctx.reply(f"✅ Added {user.mention} to the ticket.")

@bot.hybrid_command(name="unclaim")
async def unclaim(ctx):
    overwrites = ctx.channel.overwrites
    for target in list(overwrites):
        if isinstance(target, discord.Member) and target != ctx.author:
            await ctx.channel.set_permissions(target, overwrite=None)
    await ctx.reply("✅ Ticket unclaimed.")

@bot.hybrid_command(name="claim")
async def claim(ctx):
    await ctx.reply(f"✅ Ticket claimed by {ctx.author.mention}")
    log_data = config.find_one({"_id": ctx.guild.id})
    if log_data and "log_channel" in log_data:
        log_channel = ctx.guild.get_channel(log_data["log_channel"])
        if log_channel:
            await log_channel.send(f"📌 Ticket claimed by {ctx.author.mention}")

@bot.hybrid_command(name="close")
async def close(ctx):
    await ctx.channel.delete()
    log_data = config.find_one({"_id": ctx.guild.id})
    if log_data and "log_channel" in log_data:
        log_channel = ctx.guild.get_channel(log_data["log_channel"])
        if log_channel:
            await log_channel.send(f"🔒 Ticket closed by {ctx.author.mention}")

bot.run(TOKEN)
