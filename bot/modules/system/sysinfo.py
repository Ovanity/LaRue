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
    units = ["B", "KB", "MB", "GB", "TB", "PB", "EB"]
    f = float(n)
    for u in units:
        if f < 1024.0:
            return f"{f:.1f} {u}"
        f /= 1024.0
    return f"{f:.1f} ZB"

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

def _cpu_overview() -> str:
    """
    Retourne '12% — load: 0.23 0.45 0.50' si possible,
    sinon '12%' ou 'load: ...' ou 'n/a'.
    """
    pct_str = None
    load_str = None

    if psutil:
        try:
            pct = psutil.cpu_percent(interval=0.2)
            pct_str = f"{pct:.0f}%"
        except Exception:
            pct_str = None

    try:
        load1, load5, load15 = os.getloadavg()
        load_str = f"load: {load1:.2f} {load5:.2f} {load15:.2f}"
    except Exception:
        load_str = None

    if pct_str and load_str:
        return f"{pct_str} — {load_str}"
    if pct_str:
        return pct_str
    if load_str:
        return load_str
    return "n/a"

def _mem_info() -> str:
    if psutil:
        try:
            v = psutil.virtual_memory()
            return f"{_fmt_bytes(int(v.used))} / {_fmt_bytes(int(v.total))} ({v.percent:.0f}%)"
        except Exception:
            pass
    return "n/a"

def _disk_info() -> str:
    try:
        total, used, free = shutil.disk_usage("/")
        pct = (100.0 * float(used)) / float(max(1, total))
        return f"{_fmt_bytes(int(used))} / {_fmt_bytes(int(total))} ({pct:.0f}%) — free: {_fmt_bytes(int(free))}"
    except Exception:
        return "n/a"

def _ip_info() -> str:
    # Pas d'appel externe : hostname/IP locale uniquement
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

def _now_utc_hms() -> str:
    # Remplace datetime.utcnow() -> timezone-aware
    return datetime.now(UTC).strftime("%H:%M:%S UTC")


# ─────────────────────────────
# Commande
# ─────────────────────────────
def register(tree: app_commands.CommandTree, guild_obj: Optional[discord.Object], client: discord.Client):
    @tree.command(name="sysinfo", description="Dashboard système & bot (rafraîchi en direct)")
    @app_commands.guilds(guild_obj) if guild_obj else (lambda f: f)
    async def sysinfo(inter: Interaction):
        pyver = platform.python_version()
        uname = platform.uname()
        bot_ping_ms = int(getattr(client, "latency", 0.0) * 1000)

        embed = discord.Embed(
            title="🛰️ LaRue.exe — SysInfo",
            description="Diagnostic en cours…",
            color=discord.Color.dark_teal()
        )
        # Bloc Bot
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
        # Bloc Système
        embed.add_field(
            name="Système",
            value=(
                f"• **OS**: `{uname.system} {uname.release}` `{uname.machine}`\n"
                f"• **CPU**: `{_cpu_overview()}`\n"
                f"• **RAM**: `{_mem_info()}`\n"
                f"• **Disk**: `{_disk_info()}`\n"
                f"• **Uptime OS**: `{_sys_uptime()}`\n"
                f"• **Host/IP**: `{_ip_info()}`\n"
                f"• **Proc.**: `{_proc_count()}`"
            ),
            inline=False
        )
        # Bloc Console (reflète de vraies stats à chaque refresh)
        console_lines: list[str] = []
        embed.add_field(
            name="Console",
            value="```log\ncollecting metrics…\n```",
            inline=False
        )
        embed.set_footer(text=f"Emitted @ {_now_utc_hms()} • byMartin")

        await inter.response.send_message(embed=embed)
        msg = await inter.original_response()

        # 3 rafraîchissements “live”, avec mesures réelles
        for _ in range(3):
            await asyncio.sleep(1.2)

            # Mesures “vivantes”
            bot_ping_ms = int(getattr(client, "latency", 0.0) * 1000)
            cpu = _cpu_overview()
            ram = _mem_info()
            disk = _disk_info()
            procs = _proc_count()

            # Met à jour les blocs
            embed.set_field_at(
                0,
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
            embed.set_field_at(
                1,
                name="Système",
                value=(
                    f"• **OS**: `{uname.system} {uname.release}` `{uname.machine}`\n"
                    f"• **CPU**: `{cpu}`\n"
                    f"• **RAM**: `{ram}`\n"
                    f"• **Disk**: `{disk}`\n"
                    f"• **Uptime OS**: `{_sys_uptime()}`\n"
                    f"• **Host/IP**: `{_ip_info()}`\n"
                    f"• **Proc.**: `{procs}`"
                ),
                inline=False
            )

            # Ligne “logs” réalistes
            console_lines.append(
                f"{_now_utc_hms()} | ws:{bot_ping_ms}ms | cpu:{cpu} | ram:{ram} | disk:{disk} | proc:{procs}"
            )
            embed.set_field_at(
                2,
                name="Console",
                value="```log\n" + "\n".join(console_lines[-10:]) + "\n```",
                inline=False
            )

            embed.set_footer(text=f"Emitted @ {_now_utc_hms()} • byMartin")
            await msg.edit(embed=embed)


# Ancienne compat éventuelle
def setup_system_debug(tree: app_commands.CommandTree, storage, guild_id: int):
    guild_obj = discord.Object(id=guild_id) if guild_id else None
    dummy_client = discord.Client(intents=discord.Intents.none())
    register(tree, guild_obj, dummy_client)