from __future__ import annotations
import logging, importlib
import inspect
import discord
from discord import app_commands
from discord.ext import tasks

from .config import settings
from .storage import SQLiteStorage

# ── Storage
storage = SQLiteStorage(settings.data_dir)

# ── Logging
log = logging.getLogger("larue")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ── Discord client
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# Exposer les services utiles aux handlers
client.storage = storage

# ═══════════════════════════════════════════════════════════════════
# Modules à charger (1 fichier = 1 feature)
MODULES = [
    "bot.modules.system.health",
    "bot.modules.admin.admin",
    "bot.modules.rp.start",
    "bot.modules.rp.economy",
    "bot.modules.rp.shop",
    "bot.modules.system.sysinfo",
    "bot.modules.rp.tabac",

]

def _call_with_best_signature(fn, *args):
    """
    Essaie d'appeler fn avec différentes signatures courantes:
    - (tree, guild_obj, client)
    - (tree, storage, settings.guild_id)
    - (tree, guild_obj)
    - (tree, storage, guild_obj)
    - (tree,)    ← au pire
    """
    candidates = [
        (tree, discord.Object(id=settings.guild_id) if settings.guild_id else None, client),
        (tree, storage, settings.guild_id),
        (tree, discord.Object(id=settings.guild_id) if settings.guild_id else None),
        (tree, storage, discord.Object(id=settings.guild_id) if settings.guild_id else None),
        (tree,),
    ]
    for params in candidates:
        try:
            return fn(*params)
        except TypeError:
            continue
    sig = inspect.signature(fn)
    log.warning("Impossible d'appeler %s avec une signature connue (sig=%s)", fn.__name__, sig)

def _register_one_module(dotted: str):
    mod = importlib.import_module(dotted)
    # 1) Préférence: register(tree, guild_obj, client)
    if hasattr(mod, "register") and callable(mod.register):
        log.info("Register via register(): %s", dotted)
        return _call_with_best_signature(mod.register)

    # 2) Compatibilité: rechercher des fonctions setup_*
    setups = [getattr(mod, n) for n in dir(mod) if n.startswith("setup_")]
    if setups:
        for fn in setups:
            if callable(fn):
                log.info("Register via %s() in %s", fn.__name__, dotted)
                _call_with_best_signature(fn)
        return

    log.warning("Module %s: ni register() ni setup_* trouvés — ignoré.", dotted)

def _register_modules():
    for dotted in MODULES:
        try:
            _register_one_module(dotted)
        except Exception as e:
            log.exception("Échec d'enregistrement du module %s: %s", dotted, e)

# ═══════════════════════════════════════════════════════════════════

@client.event
async def on_ready():
    guild_obj = discord.Object(id=settings.guild_id) if settings.guild_id else None

    # 1) Enregistrer toutes les features avant la sync
    _register_modules()

    # 2) Sync (guild = instantané, global = propagation lente)
    try:
        if guild_obj:
            synced = await tree.sync(guild=guild_obj)
            log.info("Synced %d commands on guild %s: %s",
                     len(synced), settings.guild_id, [c.name for c in synced])
            seen = await tree.fetch_commands(guild=guild_obj)
            log.info("Guild fetch shows %d commands: %s",
                     len(seen), [c.name for c in seen])
        else:
            synced = await tree.sync()
            log.info("Synced %d GLOBAL commands: %s", len(synced), [c.name for c in synced])
    except discord.Forbidden as e:
        log.error("403 Missing Access au sync guild. Vérifie l'invite (applications.commands) et GUILD_ID. %s", e)
        synced = await tree.sync()
        log.info("Fallback: synced %d GLOBAL commands.", len(synced))
    except Exception as e:
        log.exception("Sync error: %s", e)

    if not daily_tick.is_running():
        daily_tick.start()
    log.info("LaRue connecté en %s", client.user)

@tasks.loop(hours=24)
async def daily_tick():
    log.info("Tick quotidien")

def run():
    client.run(settings.token)