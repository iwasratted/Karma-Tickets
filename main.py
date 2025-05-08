import discord
from discord.ext import commands
from discord import app_commands
import pymongo
from flask import Flask
from threading import Thread
from keep_alive import keep_alive
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Initialize the bot and database
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="$", intents=intents)

# MongoDB client setup
mongo_client = pymongo.MongoClient(os.getenv("MONGO_URI"))
db = mongo_client['karma_ticket_db']

# Flask Keep-Alive setup
app = Flask(__name__)

@app.route('/')
def home():
    return "Karma Ticket Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# Bot event
@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')

# Panel Command - Embed builder
@bot.hybrid_command(name="panel")
async def panel(ctx):
    # Step 1: Ask for the author name
    await ctx.reply("Please provide the **author name** for the embed.")
    author_name_msg = await bot.wait_for('message', check=lambda m: m.author == ctx.author)
    author_name = author_name_msg.content

    # Step 2: Ask for the embed title
    await ctx.reply("Now, provide the **embed title**.")
    title_msg = await bot.wait_for('message', check=lambda m: m.author == ctx.author)
    title = title_msg.content

    # Step 3: Ask for the embed description
    await ctx.reply("Now, provide the **embed description**.")
    description_msg = await bot.wait_for('message', check=lambda m: m.author == ctx.author)
    description = description_msg.content

    # Step 4: Ask for an image URL (optional)
    await ctx.reply("Would you like to add an **image URL**? (Type 'no' to skip.)")
    image_url_msg = await bot.wait_for('message', check=lambda m: m.author == ctx.author)
    image_url = image_url_msg.content
    if image_url.lower() == "no":
        image_url = None

    # Step 5: Construct the embed
    embed = discord.Embed(title=title, description=description, color=discord.Color.blurple())
    embed.set_author(name=author_name)

    if image_url:
        embed.set_image(url=image_url)

    # Step 6: Send the embed
    embed_msg = await ctx.channel.send(embed=embed)
    
    # Store the embed message ID for future reference
    db.config.update_one(
        {"_id": ctx.guild.id},
        {"$set": {"panel_msg": embed_msg.id}},
        upsert=True
    )

    await ctx.reply(f"✅ Embed created and sent! {embed_msg.jump_url}")

# Button Command - Create buttons (buy, sell, apply, etc.)
@bot.hybrid_command(name="button")
async def button(ctx, button_name: str, category_id: str, message_id: int):
    # Fetch embed message
    embed_msg = await ctx.channel.fetch_message(message_id)
    embed = embed_msg.embeds[0]

    # Create a button for each category (buy, sell, apply, etc.)
    if button_name.lower() == "buy":
        label = "Buy Ticket"
    elif button_name.lower() == "sell":
        label = "Sell Ticket"
    else:
        label = "Apply Ticket"
    
    # Create a button and link it to a category
    button = discord.ui.Button(label=label, style=discord.ButtonStyle.primary)
    
    # Define an interaction when the button is clicked (can be customized further)
    async def button_callback(interaction):
        await interaction.response.send_message(f"You've clicked the {label} button!", ephemeral=True)
        # Create the ticket channel based on category_id
        category = discord.utils.get(ctx.guild.categories, id=int(category_id))
        if category:
            await ctx.guild.create_text_channel(f"ticket-{interaction.user.name}", category=category)
        else:
            await ctx.reply("Invalid category ID!")

    button.callback = button_callback

    # Create an Action Row to hold the button
    action_row = discord.ui.ActionRow(button)

    # Send the embed with the button
    await embed_msg.edit(embed=embed, components=[action_row])
    await ctx.reply(f"✅ Button '{button_name}' created for the embed!")

# $rename Command - Rename the ticket channel
@bot.command(name="rename")
async def rename(ctx, new_name: str):
    if ctx.channel.name.startswith("ticket-"):
        await ctx.channel.edit(name=new_name)
        await ctx.reply(f"✅ Channel renamed to {new_name}!")
    else:
        await ctx.reply("❌ This is not a ticket channel!")

# $add Command - Add a user to the ticket
@bot.command(name="add")
async def add(ctx, member: discord.Member):
    if ctx.channel.name.startswith("ticket-"):
        await ctx.channel.set_permissions(member, read_messages=True, send_messages=True)
        await ctx.reply(f"✅ Added {member.mention} to the ticket!")
    else:
        await ctx.reply("❌ This is not a ticket channel!")

# $unclaim Command - Unclaim the ticket (remove permissions)
@bot.command(name="unclaim")
async def unclaim(ctx, member: discord.Member):
    if ctx.channel.name.startswith("ticket-"):
        await ctx.channel.set_permissions(member, read_messages=False, send_messages=False)
        await ctx.reply(f"✅ Removed {member.mention} from the ticket!")
    else:
        await ctx.reply("❌ This is not a ticket channel!")

# $claim Command - Claim the ticket (give permissions)
@bot.command(name="claim")
async def claim(ctx):
    if ctx.channel.name.startswith("ticket-"):
        await ctx.channel.set_permissions(ctx.author, read_messages=True, send_messages=True)
        await ctx.reply(f"✅ You've claimed the ticket!")
    else:
        await ctx.reply("❌ This is not a ticket channel!")

# $close Command - Close the ticket with a reason
@bot.command(name="close")
async def close(ctx, *, reason: str = "No reason provided."):
    if ctx.channel.name.startswith("ticket-"):
        await ctx.channel.send(f"Ticket closed. Reason: {reason}")
        await ctx.channel.delete()
        await ctx.reply(f"✅ Ticket closed with reason: {reason}")
    else:
        await ctx.reply("❌ This is not a ticket channel!")

# Keep the bot alive using Flask
keep_alive()

# Run the bot
bot.run(os.getenv("TOKEN"))
