# bot/modules/system/health.py
from __future__ import annotations
import time, platform, os, importlib.util
import discord
from discord import app_commands, Interaction

from bot.domain import players as d_players

# On lit la DB via le helper central (sans toucher à des chemins en dur)
try:
    from bot.core.db.base import get_conn  # type: ignore
except Exception:  # pragma: no cover
    get_conn = None  # type: ignore

BOT_START_TIME = time.time()

def _fmt_uptime(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}h {m}m {s}s"

def _sqlite_info() -> dict:
    """Retourne des infos légères sur la DB (chemin, taille, journal_mode, user_version)."""
    info: dict = {}
    if not get_conn:
        return info
    try:
        con = get_conn()
        # chemin du fichier principal
        path = None
        try:
            rows = con.execute("PRAGMA database_list;").fetchall()
            for _, name, file in rows:
                if name == "main":
                    path = file or None
                    break
        except Exception:
            pass
        if path and os.path.exists(path):
            info["db_path"] = path
            try:
                info["db_size_mb"] = os.path.getsize(path) / 1024**2
            except OSError:
                pass

        # mode journal + version de schéma (PRAGMA user_version)
        try:
            (journal_mode,) = con.execute("PRAGMA journal_mode;").fetchone()
            info["journal_mode"] = str(journal_mode).upper()
        except Exception:
            pass
        try:
            (user_version,) = con.execute("PRAGMA user_version;").fetchone()
            info["user_version"] = int(user_version or 0)
        except Exception:
            pass
    except Exception:
        pass
    return info

def register(tree: app_commands.CommandTree, guild_obj: discord.Object | None, client: discord.Client | None = None):
    """Expose /debug pour inspecter rapidement l'état du bot (test-only idéalement)."""

    @tree.command(name="debug", description="État du bot (latence, uptime, mémoire, DB, versions)")
    @app_commands.guilds(guild_obj) if guild_obj else (lambda f: f)
    async def debug_cmd(inter: Interaction):
        # Latence & uptime
        latency_ms = round(inter.client.latency * 1000) if inter.client.latency else 0
        uptime = _fmt_uptime(int(time.time() - BOT_START_TIME))

        # Mémoire (optionnel si psutil dispo)
        mem_text = "n/a"
        if importlib.util.find_spec("psutil"):
            import psutil  # type: ignore
            rss_mb = psutil.Process().memory_info().rss / 1024**2
            mem_text = f"{rss_mb:.1f} MB"

        # Compteurs domaine
        try:
            players_count = str(d_players.count())
        except Exception:
            players_count = "n/a"

        # Infos SQLite (via get_conn)
        dbi = _sqlite_info()

        embed = discord.Embed(title="🛠️ Debug LaRue.exe", color=discord.Color.blurple())
        embed.add_field(name="📡 Latence", value=f"{latency_ms} ms", inline=True)
        embed.add_field(name="⏳ Uptime", value=uptime, inline=True)
        embed.add_field(name="💾 Mémoire", value=mem_text, inline=True)
        embed.add_field(name="👥 Joueurs", value=players_count, inline=True)
        embed.add_field(name="🐍 Python", value=platform.python_version(), inline=True)
        embed.add_field(name="🤖 discord.py", value=discord.__version__, inline=True)

        # DB details (si disponibles)
        if dbi:
            if dbi.get("db_path"):
                size = dbi.get("db_size_mb")
                size_txt = f" ({size:.1f} MB)" if isinstance(size, float) else ""
                embed.add_field(name="📂 DB", value=f"{dbi['db_path']}{size_txt}", inline=False)
            jm = dbi.get("journal_mode")
            uv = dbi.get("user_version")
            if jm or uv is not None:
                parts = []
                if jm: parts.append(f"journal={jm}")
                if uv is not None: parts.append(f"user_version={uv}")
                embed.add_field(name="⚙️ SQLite", value=" • ".join(parts), inline=True)

        embed.add_field(name="📅 Maintenant", value=f"<t:{int(time.time())}:F>", inline=False)

        await inter.response.send_message(embed=embed, ephemeral=True)
