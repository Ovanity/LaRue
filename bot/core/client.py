# bot/core/client.py
from __future__ import annotations
import logging, importlib, inspect, os
import discord
from discord import app_commands
from discord.ext import tasks

from .config import settings
from .db.base import get_conn
from .db.migrations import migrate_if_needed

from bot.core.broadcast import BroadcastService
from bot.core.broadcast_scheduler import BroadcastTicker

# ── Logging
log = logging.getLogger("larue")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ── Discord client
intents = discord.Intents.default()
intents.members = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ── Guilds de test (supporte 1..n guilds)
SYNC_SCOPE = settings.sync_scope

def _list_from_env(var: str) -> list[int]:
    raw = os.getenv(var, "").strip()
    if not raw:
        return []
    out: list[int] = []
    for part in raw.split(","):
        s = part.strip()
        if s.isdigit():
            out.append(int(s))
    return out

if SYNC_SCOPE in ("guild", "both"):
    env_ids = _list_from_env("TEST_GUILD_IDS")
    if env_ids:
        TEST_GUILD_IDS = env_ids
    elif getattr(settings, "guild_id", 0):
        TEST_GUILD_IDS = [int(settings.guild_id)]
    else:
        TEST_GUILD_IDS = []
else:
    TEST_GUILD_IDS = []

TEST_GUILDS = [discord.Object(id=g) for g in TEST_GUILD_IDS]

# ═══════════════════════════════════════════════════════════════════
# Où publier chaque module
MODULES_GLOBAL = [
    "bot.modules.rp.start",
    "bot.modules.rp.economy",
    "bot.modules.rp.shop",
    "bot.modules.rp.tabac",
    "bot.modules.social.profile",
    "bot.modules.rp.recycler",
    "bot.modules.system.news",
]

MODULES_TEST_ONLY = [
    "bot.modules.system.health",
    "bot.modules.admin.admin",
    "bot.modules.system.sysinfo",
]

# Utilitaires d’enregistrement
def _call_with_best_signature(fn, guild_obj_for_register: discord.Object | None):
    candidates = [
        (tree, guild_obj_for_register, client),   # register(tree, guild, client)
        (tree, guild_obj_for_register),           # register(tree, guild)
        (tree,),                                  # register(tree)
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
        log.info("Register via register(): %s (guild=%s)", dotted, getattr(guild_obj_for_register, "id", None))
        return _call_with_best_signature(mod.register, guild_obj_for_register)

    setups = [getattr(mod, n) for n in dir(mod) if n.startswith("setup_")]
    if setups:
        for fn in setups:
            if callable(fn):
                log.info("Register via %s() in %s (guild=%s)", fn.__name__, dotted, getattr(guild_obj_for_register, "id", None))
                _call_with_best_signature(fn, guild_obj_for_register)
        return

    log.warning("Module %s: ni register() ni setup_* trouvés — ignoré.", dotted)

def _register_modules_global():
    for dotted in MODULES_GLOBAL:
        try:
            _register_one_module(dotted, None)
        except Exception as e:
            log.exception("Échec d'enregistrement global du module %s: %s", dotted, e)

def _register_modules_test_only():
    for dotted in MODULES_TEST_ONLY:
        for g in TEST_GUILDS:
            try:
                _register_one_module(dotted, g)
            except Exception as e:
                log.exception("Échec d'enregistrement test-only du module %s sur %s: %s", dotted, g.id, e)

# ═══════════════════════════════════════════════════════════════════

@client.event
async def on_ready():
    log.info("Boot: SYNC_SCOPE=%s • TEST_GUILD_IDS=%s", SYNC_SCOPE, TEST_GUILD_IDS)

    try:
        if SYNC_SCOPE == "global":
            _register_modules_global()
            _register_modules_test_only()
            g_synced = await tree.sync()
            log.info("Synced %d GLOBAL commands: %s", len(g_synced), [c.name for c in g_synced])

            if os.getenv("COPY_GLOBAL_TO_TEST", "0") == "1" and TEST_GUILDS:
                for g in TEST_GUILDS:
                    tree.copy_global_to(guild=g)
                    y_synced = await tree.sync(guild=g)
                    log.info("Copied & synced %d commands to guild %s: %s",
                             len(y_synced), g.id, [c.name for c in y_synced])

        elif SYNC_SCOPE == "guild":
            if not TEST_GUILDS:
                raise RuntimeError("SYNC_SCOPE=guild mais aucune guild de test n’est définie.")
            _register_modules_for_guilds(MODULES_GLOBAL + MODULES_TEST_ONLY, TEST_GUILDS)
            for g in TEST_GUILDS:
                synced_g = await tree.sync(guild=g)
                log.info("Synced %d commands on guild %s: %s", len(synced_g), g.id, [c.name for c in synced_g])

        else:  # "both"
            _register_modules_global()
            _register_modules_test_only()
            g_synced = await tree.sync()
            log.info("Synced %d GLOBAL commands: %s", len(g_synced), [c.name for c in g_synced])
            for g in TEST_GUILDS:
                tree.copy_global_to(guild=g)
                y_synced = await tree.sync(guild=g)
                log.info("Copied & synced %d commands to guild %s: %s",
                         len(y_synced), g.id, [c.name for c in y_synced])

    except discord.Forbidden as e:
        log.error("403 Missing Access au sync. Invite le bot sur la/les guild(s) cible(s) avec scope applications.commands. %s", e)
    except Exception as e:
        log.exception("Sync error: %s", e)

    await BroadcastService.init(client)
    BroadcastTicker.start(client)

    if not daily_tick.is_running():
        daily_tick.start()
    log.info("LaRue connecté en %s", client.user)

@tasks.loop(hours=24)
async def daily_tick():
    log.info("Tick quotidien")

def _register_modules_for_guilds(modules: list[str], guilds: list[discord.Object]):
    for dotted in modules:
        for g in guilds:
            try:
                _register_one_module(dotted, g)
            except Exception as e:
                log.exception("Échec d'enregistrement du module %s sur %s: %s", dotted, getattr(g, "id", None), e)

def run():
    # 1) Migrations au boot
    with get_conn() as con:
        migrate_if_needed(con)

    # 2) Lancement du client
    client.run(settings.token)
