from __future__ import annotations
import logging, discord
from discord import app_commands
from discord.ext import tasks
from .config import settings
from .storage import JSONStorage

log = logging.getLogger("larue")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

intents = discord.Intents.default()  # aucun privileged intent requis pour la V1
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

storage = JSONStorage(settings.data_dir)

@client.event
async def on_ready():
    if settings.guild_id:
        await tree.sync(guild=discord.Object(id=settings.guild_id))
    else:
        await tree.sync()
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
