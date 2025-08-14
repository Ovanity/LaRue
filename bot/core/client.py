from __future__ import annotations
import logging, discord
from discord import app_commands
from discord.ext import tasks
from .config import settings
from .storage import SQLiteStorage

storage = SQLiteStorage(settings.data_dir)

log = logging.getLogger("larue")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

intents = discord.Intents.default()  # aucun privileged intent requis pour la V1
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


@client.event
async def on_ready():
    try:
        if settings.guild_id:
            guild_obj = discord.Object(id=settings.guild_id)
            synced = await tree.sync(guild=guild_obj)
            log.info("Synced %d commands on guild %s: %s",
                     len(synced), settings.guild_id, [c.name for c in synced])
            # Double-check: quelles commandes le serveur voit ?
            seen = await tree.fetch_commands(guild=guild_obj)
            log.info("Guild fetch shows %d commands: %s",
                     len(seen), [c.name for c in seen])
        else:
            synced = await tree.sync()
            log.info("Synced %d GLOBAL commands: %s", len(synced), [c.name for c in synced])
    except Exception as e:
        log.exception("Sync error: %s", e)

    if not daily_tick.is_running():
        daily_tick.start()
    log.info("LaRue connecté en %s", client.user)

@tasks.loop(hours=24)
async def daily_tick():
    log.info("Tick quotidien")

def run():
    # import tardif pour enregistrer les commandes
    from bot.modules.system.health import setup_system
    from bot.modules.rp.commands import setup_rp
    setup_system(tree, storage, settings.guild_id)
    setup_rp(tree, storage, settings.guild_id)
    client.run(settings.token)
