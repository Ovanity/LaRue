from __future__ import annotations
import logging
import discord
from discord import app_commands
from discord.ext import tasks

from .config import settings
from .storage import SQLiteStorage   # ← SQLite forcé (change si tu veux un switch)

# ── Storage
storage = SQLiteStorage(settings.data_dir)

# ── Logging
log = logging.getLogger("larue")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ── Discord client
intents = discord.Intents.default()  # aucun privileged intent requis pour la V1
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# Expose le storage au client pour y accéder dans les handlers (/ruelle, /start, etc.)
client.storage = storage  # ⬅ important

@client.event
async def on_ready():
    # 1) Enregistrer les modules AVANT la sync
    guild_obj = discord.Object(id=settings.guild_id) if settings.guild_id else None
    try:
        from bot.modules.system.health import setup_system
        from bot.modules.rp.start import setup_start
        from bot.modules.rp.economy import setup_economy

        setup_system(tree, storage, settings.guild_id)  # module système existant (/ping, /stats)
        setup_start(tree, guild_obj)                    # /start
        setup_economy(tree, guild_obj)                  # /ruelle mendier|fouiller

        # 2) Sync (guild = instantané, global = propagation plus lente)
        if guild_obj:
            synced = await tree.sync(guild=guild_obj)
            log.info("Synced %d commands on guild %s: %s",
                     len(synced), settings.guild_id, [c.name for c in synced])
            # double-check côté API
            seen = await tree.fetch_commands(guild=guild_obj)
            log.info("Guild fetch shows %d commands: %s",
                     len(seen), [c.name for c in seen])
        else:
            synced = await tree.sync()
            log.info("Synced %d GLOBAL commands: %s", len(synced), [c.name for c in synced])

    except discord.Forbidden as e:
        log.error("403 Missing Access lors du sync guild. Vérifie l'invite (scope applications.commands) et GUILD_ID. %s", e)
        # Fallback global pour éviter de bloquer le démarrage :
        synced = await tree.sync()
        log.info("Fallback: synced %d GLOBAL commands.", len(synced))
    except Exception as e:
        log.exception("Sync error: %s", e)

    # 3) Tâche planifiée
    if not daily_tick.is_running():
        daily_tick.start()

    log.info("LaRue connecté en %s", client.user)

@tasks.loop(hours=24)
async def daily_tick():
    log.info("Tick quotidien")

def run():
    client.run(settings.token)