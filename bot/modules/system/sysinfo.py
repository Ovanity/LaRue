# bot/modules/system/sysinfo.py
from __future__ import annotations
import os, time, platform, shutil, socket, asyncio
from datetime import datetime, UTC
from typing import Optional

import discord
from discord import app_commands, Interaction

try:
    import psutil  # facultatif mais utile
except Exception:
    psutil = None  # type: ignore

STARTED_AT = time.time()  # approximation du démarrage du bot (process)


# ─────────────────────────────
# Helpers formatage
# ─────────────────────────────
def _fmt_bytes(n: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    f = float(n)
    for u in units:
        if f < 1024.0:
            return f"{f:.1f} {u}"
        f /= 1024.0
    return f"{f:.1f} EB"

def _uptime_str(seconds: int) -> str:
    seconds = int(max(0, seconds))
    d, r = divmod(seconds, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    parts.append(f"{s}s")
    return " ".join(parts)

def _bot_uptime() -> str:
    return _uptime_str(int(time.time() - STARTED_AT))

def _sys_uptime() -> str:
    if psutil:
        try:
            return _uptime_str(int(time.time() - int(psutil.boot_time())))
        except Exception:
            pass
    # Fallback Linux
    try:
        with open("/proc/uptime", "r") as f:
            seconds = float(f.read().split()[0])
            return _uptime_str(int(seconds))
    except Exception:
        return "n/a"

def _cpu_load() -> str:
    # charge moyenne si dispo (Unix)
    try:
        load1, load5, load15 = os.getloadavg()
        return f"{load1:.2f} {load5:.2f} {load15:.2f}"
    except Exception:
        # sur Windows, psutil peut aider
        if psutil:
            try:
                return f"{psutil.cpu_percent(interval=0.2):.0f}%"
            except Exception:
                pass
        return "n/a"

def _mem_info() -> str:
    if psutil:
        try:
            v = psutil.virtual_memory()
            return f"{_fmt_bytes(int(v.used))} / {_fmt_bytes(int(v.total))} ({v.percent:.0f}%)"
        except Exception:
            pass
    # fallback très basique
    return "n/a"

def _disk_info() -> str:
    try:
        total, used, free = shutil.disk_usage("/")
        pct = (100.0 * float(used)) / float(max(1, total))
        return f"{_fmt_bytes(int(used))} / {_fmt_bytes(int(total))} ({pct:.0f}%) — free: {_fmt_bytes(int(free))}"
    except Exception:
        return "n/a"

def _ip_info() -> str:
    # Pas d'appel externe : on se limite au hostname/IP locale
    try:
        host = socket.gethostname()
        ip = socket.gethostbyname(host)
        return f"{host} ({ip})"
    except Exception:
        return "n/a"

def _proc_count() -> str:
    if psutil:
        try:
            return str(len(psutil.pids()))
        except Exception:
            pass
    return "n/a"


# ─────────────────────────────
# Commande
# ─────────────────────────────
def register(tree: app_commands.CommandTree, guild_obj: Optional[discord.Object], client: discord.Client):
    @tree.command(name="sysinfo", description="Dashboard système & bot (avec logs en temps réel)")
    @app_commands.guilds(guild_obj) if guild_obj else (lambda f: f)
    async def sysinfo(inter: Interaction):
        # Récup métriques “instant”
        pyver = platform.python_version()
        uname = platform.uname()
        bot_ping_ms = int(getattr(client, "latency", 0.0) * 1000)

        embed = discord.Embed(
            title="🛰️ LaRue.exe — SysInfo",
            description="Diagnostic en cours… *stand by*",
            color=discord.Color.dark_teal()
        )
        embed.add_field(
            name="Bot",
            value=(
                f"• **Ping WS**: `{bot_ping_ms} ms`\n"
                f"• **Uptime**: `{_bot_uptime()}`\n"
                f"• **Guilds**: `{len(getattr(client, 'guilds', []))}`\n"
                f"• **Cmds**: `{len(getattr(tree, 'commands', []))}`\n"
                f"• **Python**: `{pyver}`"
            ),
            inline=False
        )
        embed.add_field(
            name="Système",
            value=(
                f"• **OS**: `{uname.system} {uname.release}` `{uname.machine}`\n"
                f"• **CPU**: `{_cpu_load()}` (load/%)\n"
                f"• **RAM**: `{_mem_info()}`\n"
                f"• **Disk**: `{_disk_info()}`\n"
                f"• **Uptime OS**: `{_sys_uptime()}`\n"
                f"• **Host/IP**: `{_ip_info()}`\n"
                f"• **Proc.**: `{_proc_count()}`"
            ),
            inline=False
        )

        # zone “console” qui sera mise à jour
        console_lines = [
            "boot > init modules…",
            "net  > opening sockets…",
            "db   > warming up cache…",
        ]
        embed.add_field(
            name="Console",
            value="```log\n" + "\n".join(console_lines) + "\n```",
            inline=False
        )
        # ✅ timezone-aware (remplace datetime.utcnow)
        embed.set_footer(text=f"Emitted @ {datetime.now(UTC).strftime('%H:%M:%S UTC')} • stay low-key")

        await inter.response.send_message(embed=embed)
        msg = await inter.original_response()

        # ── Simulation de “live logs” (3 edits)
        steps = [
            ["ok   > modules ready", "ok   > sockets bound", "ok   > cache primed"],
            ["scan > ports: 80, 443…", "scan > nothing spicy (pour l’instant)"],
            [f"ws   > ping {int(getattr(client,'latency',0.0)*1000)}ms stable", "final> system nominal • enjoy"],
        ]

        for chunk in steps:
            await asyncio.sleep(1.2)  # petit délai pour le show
            console_lines.extend(chunk)
            # On rafraîchit aussi quelques métriques “vivantes”
            embed.set_field_at(
                0,
                name="Bot",
                value=(
                    f"• **Ping WS**: `{int(getattr(client,'latency',0.0)*1000)} ms`\n"
                    f"• **Uptime**: `{_bot_uptime()}`\n"
                    f"• **Guilds**: `{len(getattr(client, 'guilds', []))}`\n"
                    f"• **Cmds**: `{len(getattr(tree, 'commands', []))}`\n"
                    f"• **Python**: `{pyver}`"
                ),
                inline=False
            )
            embed.set_field_at(
                2,
                name="Console",
                value="```log\n" + "\n".join(console_lines[-12:]) + "\n```",
                inline=False
            )
            # timestamp à jour (UTC)
            embed.set_footer(text=f"Emitted @ {datetime.now(UTC).strftime('%H:%M:%S UTC')} • stay low-key")
            await msg.edit(embed=embed)


# Ancien style de compat éventuelle
def setup_system_debug(tree: app_commands.CommandTree, storage, guild_id: int):
    guild_obj = discord.Object(id=guild_id) if guild_id else None
    # On ne dépend pas de storage ici, on passe client=None ⇒ ping affichera 0ms
    dummy_client = discord.Client(intents=discord.Intents.none())
    register(tree, guild_obj, dummy_client)