# main.py
import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import datetime
import re
import os
from threading import Thread
import uvicorn
from fastapi import FastAPI

# === CONFIG ===
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# Anti-spam
user_message_count = {}

# FastAPI pour le ping
app = FastAPI()

@app.get("/")
async def home():
    return {"status": "alive", "bot": str(bot.user)}

# === Lancer le serveur web en parallèle ===
def run_web():
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))

# === Événements bot ===
@bot.event
async def on_ready():
    print(f"{bot.user} est en ligne !")
    try:
        synced = await tree.sync()
        print(f"{len(synced)} commandes slash synchronisées.")
    except Exception as e:
        print(e)

    # Lancer le serveur web
    Thread(target=run_web, daemon=True).start()

# === COMMANDES SLASH (même code que avant) ===
@tree.command(name="kick", description="Expulse un membre")
@app_commands.describe(member="Membre", reason="Raison")
@app_commands.default_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "Aucune raison"):
    if member.top_role >= interaction.user.top_role:
        return await interaction.response.send_message("Tu ne peux pas expulser ce membre.", ephemeral=True)
    await member.kick(reason=reason)
    await interaction.response.send_message(f"{member.mention} expulsé ! Raison : {reason}")

@tree.command(name="ban", description="Bannir un membre")
@app_commands.describe(member="Membre", reason="Raison")
@app_commands.default_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "Aucune raison"):
    if member.top_role >= interaction.user.top_role:
        return await interaction.response.send_message("Tu ne peux pas bannir ce membre.", ephemeral=True)
    await member.ban(reason=reason)
    await interaction.response.send_message(f"{member.mention} banni ! Raison : {reason}")

@tree.command(name="mute", description="Mute un membre")
@app_commands.describe(member="Membre", time="Durée (10s, 5m, 1h, 1d)", reason="Raison")
@app_commands.default_permissions(manage_roles=True)
async def mute(interaction: discord.Interaction, member: discord.Member, time: str = None, reason: str = "Aucune raison"):
    muted_role = discord.utils.get(interaction.guild.roles, name="Muted")
    if not muted_role:
        muted_role = await interaction.guild.create_role(name="Muted")
        for channel in interaction.guild.channels:
            await channel.set_permissions(muted_role, send_messages=False, speak=False)

    if muted_role in member.roles:
        return await interaction.response.send_message("Déjà muté.", ephemeral=True)

    await member.add_roles(muted_role, reason=reason)

    if time and (duration := parse_time(time)):
        await interaction.response.send_message(f"{member.mention} muté pour **{time}**.")
        await asyncio.sleep(duration)
        if muted_role in member.roles:
            await member.remove_roles(muted_role)
            await interaction.channel.send(f"{member.mention} démute.")
    else:
        await interaction.response.send_message(f"{member.mention} muté indéfiniment.")

@tree.command(name="unmute", description="Démute un membre")
@app_commands.describe(member="Membre")
@app_commands.default_permissions(manage_roles=True)
async def unmute(interaction: discord.Interaction, member: discord.Member):
    muted_role = discord.utils.get(interaction.guild.roles, name="Muted")
    if muted_role and muted_role in member.roles:
        await member.remove_roles(muted_role)
        await interaction.response.send_message(f"{member.mention} démute.")
    else:
        await interaction.response.send_message("Pas muté.", ephemeral=True)

@tree.command(name="clear", description="Supprime X messages")
@app_commands.describe(amount="Nombre (max 100)")
@app_commands.default_permissions(manage_messages=True)
async def clear(interaction: discord.Interaction, amount: int = 5):
    if amount > 100:
        return await interaction.response.send_message("Max 100.", ephemeral=True)
    await interaction.channel.purge(limit=amount)
    await interaction.response.send_message(f"{amount} messages supprimés.", ephemeral=True)

# === ANTI-SPAM ===
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    user_id = message.author.id
    now = datetime.datetime.utcnow()
    user_message_count[user_id] = user_message_count.get(user_id, [])
    user_message_count[user_id].append(now)
    user_message_count[user_id] = [t for t in user_message_count[user_id] if (now - t).total_seconds() < 3]

    if len(user_message_count[user_id]) > 5:
        muted_role = discord.utils.get(message.guild.roles, name="Muted")
        if not muted_role:
            muted_role = await message.guild.create_role(name="Muted")
            for channel in message.guild.channels:
                await channel.set_permissions(muted_role, send_messages=False)
        await message.author.add_roles(muted_role, reason="Spam")
        await message.channel.send(f"{message.author.mention} muté pour spam.")
        user_message_count[user_id].clear()
        await asyncio.sleep(60)
        if muted_role in message.author.roles:
            await message.author.remove_roles(muted_role)
            await message.channel.send(f"{message.author.mention} démute.")

    await bot.process_commands(message)

# === Parse time ===
def parse_time(t):
    d = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    m = re.match(r"(\d+)([smhd])", t.lower())
    return int(m[1]) * d[m[2]] if m else None

# === LANCER LE BOT ===
if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))