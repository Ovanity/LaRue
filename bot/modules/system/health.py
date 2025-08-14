from __future__ import annotations
import time, platform, os, importlib.util
import discord
from discord import app_commands, Interaction

BOT_START_TIME = time.time()

def _fmt_uptime(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}h {m}m {s}s"

def register(tree: app_commands.CommandTree, guild_obj: discord.Object | None, client: discord.Client):
    """Expose /debug pour inspecter rapidement l'état du bot."""

    @tree.command(name="debug", description="État du bot (latence, uptime, mémoire, DB, versions)")
    @app_commands.guilds(guild_obj) if guild_obj else (lambda f: f)
    async def debug_cmd(inter: Interaction):
        # Latence & uptime
        latency_ms = round(inter.client.latency * 1000) if inter.client.latency else 0
        uptime = _fmt_uptime(int(time.time() - BOT_START_TIME))

        # Mémoire (optionnel si psutil n’est pas installé)
        mem_text = "n/a"
        if importlib.util.find_spec("psutil"):
            import psutil  # type: ignore
            rss_mb = psutil.Process().memory_info().rss / 1024**2
            mem_text = f"{rss_mb:.1f} MB"

        # DB path & stats joueurs (si SQLiteStorage avec db_path, sinon juste le backend)
        storage = getattr(client, "storage", None)
        backend = storage.__class__.__name__ if storage else "n/a"
        db_path = getattr(storage, "db_path", None)
        players_count = "n/a"
        try:
            if hasattr(storage, "count_players"):
                players_count = str(storage.count_players())
            else:
                # fallback générique si tu n’as pas count_players()
                if hasattr(storage, "db_path") and os.path.exists(storage.db_path):
                    # tentative simple: compter les lignes si table players existe
                    import sqlite3
                    con = sqlite3.connect(storage.db_path)
                    cur = con.cursor()
                    cur.execute("SELECT count(name) FROM sqlite_master WHERE type='table' AND name='players';")
                    if cur.fetchone()[0] == 1:
                        cur.execute("SELECT COUNT(*) FROM players;")
                        players_count = str(cur.fetchone()[0])
                    con.close()
                elif hasattr(storage, "path") and os.path.exists(storage.path):
                    # JSON fallback: longueur du dict
                    import json
                    data = json.loads(open(storage.path, "r", encoding="utf-8").read())
                    players_count = str(len(data))
        except Exception:
            pass

        embed = discord.Embed(title="🛠️ Debug LaRue.exe", color=discord.Color.blurple())
        embed.add_field(name="📡 Latence", value=f"{latency_ms} ms", inline=True)
        embed.add_field(name="⏳ Uptime", value=uptime, inline=True)
        embed.add_field(name="💾 Mémoire", value=mem_text, inline=True)
        embed.add_field(name="🗄️ Storage", value=backend, inline=True)
        if db_path:
            try:
                size_mb = os.path.getsize(db_path) / 1024**2
                embed.add_field(name="📂 DB", value=f"{db_path} ({size_mb:.1f} MB)", inline=False)
            except OSError:
                embed.add_field(name="📂 DB", value=str(db_path), inline=False)
        embed.add_field(name="👥 Joueurs", value=players_count, inline=True)
        embed.add_field(name="🐍 Python", value=platform.python_version(), inline=True)
        embed.add_field(name="🤖 discord.py", value=discord.__version__, inline=True)
        embed.add_field(name="📅 Maintenant", value=f"<t:{int(time.time())}:F>", inline=False)

        await inter.response.send_message(embed=embed, ephemeral=True)