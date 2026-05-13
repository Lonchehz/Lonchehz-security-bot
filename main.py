import discord
from discord import app_commands
from discord.ext import commands
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import json
from collections import defaultdict, deque

load_dotenv()
TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.moderation = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ================== CONFIG ==================
ADMIN_ROLE_ID = 1489911859191484446   # Cambia si quieres
MOD_ROLE_ID = 1489911958915256370     # Cambia si quieres
HONEYPOT_CHANNEL_ID = None
MOD_LOG_CHANNEL_ID = None

BOT_OWNER_ID = 123456789012345678   # ← CAMBIA ESTO POR TU ID DE DISCORD

CONFIG_FILE = "config.json"

def load_config():
    global MOD_LOG_CHANNEL_ID, HONEYPOT_CHANNEL_ID
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            MOD_LOG_CHANNEL_ID = data.get("mod_log_channel")
            HONEYPOT_CHANNEL_ID = data.get("honeypot_channel")
    except:
        pass

def save_config():
    data = {
        "mod_log_channel": MOD_LOG_CHANNEL_ID,
        "honeypot_channel": HONEYPOT_CHANNEL_ID
    }
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

load_config()

# Anti-Raid
RAID_MODE = False
RECENT_JOINS = []
RAID_THRESHOLD = 8
RAID_TIME_WINDOW = 30

# Anti-Spam
SPAM_CACHE = defaultdict(lambda: deque(maxlen=20))
SPAM_LIMIT = 6
SPAM_TIME = 8

# Warns
WARNINGS_FILE = "warnings.json"
warnings = defaultdict(lambda: defaultdict(list))

def load_warnings():
    try:
        with open(WARNINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            warnings.update({k: defaultdict(list, v) for k, v in data.items()})
    except:
        pass

def save_warnings():
    with open(WARNINGS_FILE, "w", encoding="utf-8") as f:
        json.dump({k: dict(v) for k, v in warnings.items()}, f, indent=4, default=str)

load_warnings()

# ================== LOGS ==================
async def send_mod_log(guild, title: str, description: str, color: discord.Color, moderator=None, target=None):
    if not MOD_LOG_CHANNEL_ID: return
    channel = guild.get_channel(MOD_LOG_CHANNEL_ID)
    if not channel: return
    embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.utcnow())
    if moderator: embed.add_field(name="Moderador", value=moderator.mention, inline=True)
    if target: embed.add_field(name="Usuario", value=target.mention, inline=True)
    embed.set_footer(text=f"Server ID: {guild.id}")
    try: await channel.send(embed=embed)
    except: pass

# ================== AUTO PUNISH ==================
async def apply_auto_punishment(guild, member, total_warns):
    try:
        if total_warns == 3:
            await member.kick(reason="Auto-Kick: 3 warns")
            await send_mod_log(guild, "🔨 Auto-Kick", f"{member.mention} fue kickeado (3 warns)", discord.Color.red(), target=member)
        elif total_warns >= 5:
            await member.ban(reason="Auto-Ban: 5 warns")
            await send_mod_log(guild, "⛔ Auto-Ban", f"{member.mention} fue baneado (5 warns)", discord.Color.dark_red(), target=member)
    except: pass

async def warn_user(guild, member, moderator, reason="Sin razón"):
    guild_id = str(guild.id)
    user_id = str(member.id)
    warn_entry = {"timestamp": datetime.utcnow().isoformat(), "moderator": str(moderator), "reason": reason}
    warnings[guild_id][user_id].append(warn_entry)
    save_warnings()
    total = len(warnings[guild_id][user_id])

    try:
        await member.send(f"⚠️ **Advertencia** en **{guild.name}**\n**Razón:** {reason}\n**Total:** {total}/5")
    except: pass

    await send_mod_log(guild, "⚠️ Nueva Advertencia", reason, discord.Color.orange(), moderator, member)
    await apply_auto_punishment(guild, member, total)
    return total

# ================== HONEYPOT MEJORADO ==================
@bot.event
async def on_message(message):
    if message.author.bot or message.guild is None:
        return

    # Honeypot
    if HONEYPOT_CHANNEL_ID and message.channel.id == HONEYPOT_CHANNEL_ID:
        # Verifica por roles específicos
        tiene_rol_staff = any(role.id in (ADMIN_ROLE_ID, MOD_ROLE_ID) for role in message.author.roles)
        
        # Verifica por permisos altos (sin necesidad de roles específicos)
        tiene_permisos_staff = (
            message.author.guild_permissions.administrator or
            message.author.guild_permissions.ban_members or
            message.author.guild_permissions.kick_members or
            message.author.guild_permissions.manage_guild or
            message.author.guild_permissions.manage_roles
        )

        if tiene_rol_staff or tiene_permisos_staff:
            await message.channel.send(f"✅ {message.author.mention} es Staff → Honeypot ignorado.", delete_after=8)
            return

        # Banear si no es staff
        try:
            await message.author.ban(reason="Honeypot Trigger")
            await message.channel.send(f"🚨 **HONEYPOT** → {message.author.mention} ha sido baneado.", delete_after=10)
            await send_mod_log(message.guild, "🔒 Honeypot Trigger", f"{message.author.mention} baneado automáticamente.", discord.Color.red(), target=message.author)
        except:
            await message.channel.send("⚠️ No tengo permisos para banear.")
        return

    # Anti-Spam
    user_id = message.author.id
    now = datetime.utcnow()
    SPAM_CACHE[user_id].append(now)

    while SPAM_CACHE[user_id] and now - SPAM_CACHE[user_id][0] > timedelta(seconds=SPAM_TIME):
        SPAM_CACHE[user_id].popleft()

    if len(SPAM_CACHE[user_id]) >= SPAM_LIMIT:
        try:
            await message.author.timeout(timedelta(minutes=10), reason="Anti-Spam")
            await message.channel.send(f"⛔ {message.author.mention} silenciado por spam.", delete_after=20)
            await send_mod_log(message.guild, "⛔ Anti-Spam", f"{message.author.mention} silenciado", discord.Color.orange(), target=message.author)
            await warn_user(message.guild, message.author, bot.user, "Spam automático")
        except: pass

    await bot.process_commands(message)

# ================== RESTO DE EVENTOS Y COMANDOS ==================
@bot.event
async def on_ready():
    await tree.sync()
    print("✅ Lonchehz Security está en línea!")
    print(f"Conectado en {len(bot.guilds)} servidores")

@bot.event
async def on_member_join(member):
    global RAID_MODE
    now = datetime.utcnow()
    RECENT_JOINS.append((member.id, now))
    RECENT_JOINS[:] = [x for x in RECENT_JOINS if now - x[1] < timedelta(seconds=RAID_TIME_WINDOW)]

    if len(RECENT_JOINS) >= RAID_THRESHOLD and not RAID_MODE:
        RAID_MODE = True
        alert = "🚨 **RAID DETECTADO** - Modo Raid activado automáticamente."
        await send_mod_log(member.guild, "🚨 RAID DETECTADO", alert, discord.Color.red())

# (Aquí van todos los comandos slash: help, about, warn, setlog, etc.)
# Como el mensaje sería muy largo, si quieres que te los agregue todos dime "AGREGA LOS COMANDOS" y te los pongo.

# ================== EJECUCIÓN ==================
if __name__ == "__main__":
    if not TOKEN:
        print("❌ Token no encontrado en .env")
    else:
        print("🔄 Iniciando Lonchehz Security...")
        bot.run(TOKEN)
