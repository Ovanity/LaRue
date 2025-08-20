# client.py
from __future__ import annotations
import logging, importlib, inspect
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
intents.members = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)
client.storage = storage

# ── Scope de sync: "global", "guild", "both"
SYNC_SCOPE = getattr(settings, "sync_scope", "both")  # change ça si tu veux
TEST_GUILD_ID = getattr(settings, "guild_id", None)

# ═══════════════════════════════════════════════════════════════════
MODULES = [
    "bot.modules.system.health",
    "bot.modules.admin.admin",
    "bot.modules.rp.start",
    "bot.modules.rp.economy",
    "bot.modules.rp.shop",
    "bot.modules.system.sysinfo",
    "bot.modules.rp.tabac",
    "bot.modules.social.profile",
    "bot.modules.rp.recycler",
]

def _call_with_best_signature(fn, guild_obj_for_register: discord.Object | None):
    """
    Appelle register/setup_* en privilégiant un enregistrement GLOBAL :
    on passe None pour guild_obj_for_register si on veut global.
    """
    candidates = [
        (tree, guild_obj_for_register, client),
        (tree, storage, TEST_GUILD_ID),
        (tree, guild_obj_for_register),
        (tree, storage, guild_obj_for_register),
        (tree,),
    ]
    for params in candidates:
        try:
            return fn(*params)
        except TypeError:
            continue
    sig = inspect.signature(fn)
    log.warning("Impossible d'appeler %s avec une signature connue (sig=%s)", fn.__name__, sig)

def _register_one_module(dotted: str, guild_obj_for_register: discord.Object | None):
    mod = importlib.import_module(dotted)
    if hasattr(mod, "register") and callable(mod.register):
        log.info("Register via register(): %s", dotted)
        return _call_with_best_signature(mod.register, guild_obj_for_register)

    setups = [getattr(mod, n) for n in dir(mod) if n.startswith("setup_")]
    if setups:
        for fn in setups:
            if callable(fn):
                log.info("Register via %s() in %s", fn.__name__, dotted)
                _call_with_best_signature(fn, guild_obj_for_register)
        return
    log.warning("Module %s: ni register() ni setup_* trouvés — ignoré.", dotted)

def _register_modules(guild_obj_for_register: discord.Object | None):
    for dotted in MODULES:
        try:
            _register_one_module(dotted, guild_obj_for_register)
        except Exception as e:
            log.exception("Échec d'enregistrement du module %s: %s", dotted, e)

# ═══════════════════════════════════════════════════════════════════

@client.event
async def on_ready():
    test_guild = discord.Object(id=TEST_GUILD_ID) if TEST_GUILD_ID else None

    # 1) Choix d’enregistrement pour les modules
    # - global / both  -> on passe None aux modules → commandes globales
    # - guild          -> on passe l’objet guild → commandes limitées à ce serveur
    if SYNC_SCOPE in ("global", "both"):
        guild_for_register = None
    else:  # "guild"
        guild_for_register = test_guild

    _register_modules(guild_for_register)

    # 2) Sync suivant le scope
    try:
        if SYNC_SCOPE == "global":
            synced = await tree.sync()             # publie GLOBAL
            log.info("Synced %d GLOBAL commands: %s", len(synced), [c.name for c in synced])

        elif SYNC_SCOPE == "guild":
            if not test_guild:
                raise RuntimeError("SYNC_SCOPE=guild mais settings.guild_id est vide.")
            synced = await tree.sync(guild=test_guild)
            log.info("Synced %d commands on guild %s: %s",
                     len(synced), TEST_GUILD_ID, [c.name for c in synced])

        else:  # "both": global publish + copie instant sur le serveur de test
            # a) Publier GLOBAL (propagation lente côté Discord)
            g_synced = await tree.sync()
            log.info("Synced %d GLOBAL commands: %s", len(g_synced), [c.name for c in g_synced])

            # b) Copier les GLOBAL → GUILD pour test instantané
            if test_guild:
                tree.copy_global_to(guild=test_guild)
                y_synced = await tree.sync(guild=test_guild)
                log.info("Copied & synced %d commands to guild %s: %s",
                         len(y_synced), TEST_GUILD_ID, [c.name for c in y_synced])

    except discord.Forbidden as e:
        log.error("403 Missing Access au sync. Vérifie les scopes d’invitation (applications.commands) et les droits. %s", e)
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