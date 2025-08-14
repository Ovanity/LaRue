from __future__ import annotations
import random
import time
import datetime as _dt
import discord
from discord import app_commands, Interaction

# ───────── Paramètres d'équilibrage LaRue.exe ─────────
# Cooldowns (en secondes)
MENDIER_COOLDOWN_S  = 60 * 60        # 1h
FOUILLER_COOLDOWN_S = 60 * 60 * 6    # 6h
# Limites quotidiennes
MENDIER_DAILY_CAP   = 12             # 12/jour
FOUILLER_DAILY_CAP  = 2              # 2/jour


# ─────────────────────────────
# Utils (classement + cooldown UX)
# ─────────────────────────────
def _medal(rank: int) -> str:
    return "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else "🏅"

def _format_leaderboard(rows: list[tuple[str | int, int]]) -> str:
    """rows: [(user_id, money), ...]"""
    lines: list[str] = []
    for i, (uid, money) in enumerate(rows, start=1):
        mention = f"<@{int(uid)}>"  # mention cliquable (pas de ping dans un embed)
        lines.append(f"**{i:>2}.** {mention} — **{money}€** {_medal(i)}")
    return "\n".join(lines)

# --- Barre de progression (10 cases)
def _progress_bar(elapsed: int, total: int, width: int = 10) -> tuple[str, int]:
    if total <= 0:
        return "──────────", 100
    pct = max(0.0, min(1.0, elapsed / total))
    filled = int(round(pct * width))
    bar = "█" * filled + "─" * (width - filled)
    return bar, int(pct * 100)

def _next_utc_midnight_epoch() -> int:
    now = _dt.datetime.utcnow()
    nxt = (now + _dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(nxt.timestamp())

def _cooldown_message(storage, user_id: int, action: str, wait: int, remaining: int, total_cd: int) -> str:
    """Message plus parlant pour un cooldown en cours (timestamps + barre de progression)."""
    now = int(time.time())
    available_at = now + int(wait)

    # Essaie de récupérer last_ts pour la progression
    last_ts = None
    if hasattr(storage, "get_action_state"):
        st = storage.get_action_state(user_id, action)
        last_ts = int(st.get("last_ts", 0)) or None

    # Barre de progression
    if last_ts:
        elapsed = max(0, now - last_ts)
        bar, pct = _progress_bar(elapsed, max(total_cd, 1))
        prog = f"`{bar}` {pct}%"
    else:
        prog = "`──────────` 0%"

    # Timestamps Discord
    rel = f"<t:{available_at}:R>"   # ex: "dans 5 heures"
    abs_t = f"<t:{available_at}:T>" # ex: "14:37"

    suffix = f"(reste **{remaining}** fois aujourd’hui)" if remaining > 0 else ""
    return f"⏳ Trop pressé. Prochaine tentative {rel} • {abs_t} {suffix}\n{prog}"

def _daily_cap_message() -> str:
    reset_at = _next_utc_midnight_epoch()
    return f"⛔ T’as tout claqué aujourd’hui. Reset {f'<t:{reset_at}:R>'} • {f'<t:{reset_at}:T>'}"

def _check_limit(storage, user_id: int, action: str, cd: int, cap: int) -> tuple[bool, str | None]:
    """
    Retourne (ok, message_si_refus). Si storage n'a pas la méthode -> toujours OK.
    """
    if not hasattr(storage, "check_and_touch_action"):
        return True, None

    ok, wait, remaining = storage.check_and_touch_action(user_id, action, cd, cap)
    if ok:
        return True, None
    # Quota du jour atteint
    if remaining == 0:
        return False, _daily_cap_message()
    # Cooldown restant
    return False, _cooldown_message(storage, user_id, action, wait, remaining, cd)


# ─────────────────────────────
# Actions réutilisables (pour start.py et slash)
# ─────────────────────────────
def mendier_action(storage, user_id: int) -> dict:
    p = storage.get_player(user_id)
    gain = random.randint(1, 8)
    if hasattr(storage, "add_money"):
        pp = storage.add_money(user_id, gain)
    else:
        pp = storage.update_player(user_id, money=p["money"] + gain)
    return {
        "money": pp["money"],
        "delta": gain,
        "msg": f"Tu tends la main… +{gain}€ • Total {pp['money']}€",
    }

def fouiller_action(storage, user_id: int) -> dict:
    p = storage.get_player(user_id)
    r = random.random()
    if r < 0.6:
        gain = random.randint(2, 15)
        if hasattr(storage, "add_money"):
            pp = storage.add_money(user_id, gain)
        else:
            pp = storage.update_player(user_id, money=p["money"] + gain)
        return {"money": pp["money"], "delta": gain, "msg": f"Quelques pièces: +{gain}€ • Total {pp['money']}€"}
    elif r < 0.9:
        return {"money": p["money"], "delta": 0, "msg": "Rien d’intéressant."}
    else:
        perte = min(5, p["money"])
        pp = storage.update_player(user_id, money=max(0, p["money"] - perte))
        return {"money": pp["money"], "delta": -perte, "msg": f"Tu glisses, ça tourne mal. -{perte}€ • Total {pp['money']}€"}

def stats_action(storage, user_id: int) -> str:
    p = storage.get_player(user_id)
    if not p or not p.get("has_started"):
        return "🚀 Tu n'as pas encore commencé ton aventure. Utilise **/start** pour débuter !"
    return f"💼 Argent: {p['money']}€"


# ─────────────────────────────
# Enregistrement des commandes
# ─────────────────────────────
def _build_group() -> app_commands.Group:
    return app_commands.Group(
        name="hess",
        description="La débrouille: mendier, fouiller, survivre."
    )

def register(tree: app_commands.CommandTree, guild_obj: discord.Object | None, client: discord.Client | None = None):
    """
    Enregistre les commandes slash :
      /hess mendier  •  /hess fouiller  •  /hess classement  •  /stats
    """
    hess = _build_group()

    @hess.command(name="mendier", description="Gagne quelques pièces")
    async def mendier(inter: Interaction):
        storage = inter.client.storage
        p = storage.get_player(inter.user.id)
        if not p.get("has_started"):
            await inter.response.send_message("Utilise /start avant.", ephemeral=True)
            return

        ok, msg = _check_limit(storage, inter.user.id, "mendier", MENDIER_COOLDOWN_S, MENDIER_DAILY_CAP)
        if not ok:
            await inter.response.send_message(msg, ephemeral=True)
            return

        res = mendier_action(storage, inter.user.id)
        await inter.response.send_message(res["msg"])

    @hess.command(name="fouiller", description="Fouille une poubelle")
    async def fouiller(inter: Interaction):
        storage = inter.client.storage
        p = storage.get_player(inter.user.id)
        if not p.get("has_started"):
            await inter.response.send_message("Utilise /start avant.", ephemeral=True)
            return

        ok, msg = _check_limit(storage, inter.user.id, "fouiller", FOUILLER_COOLDOWN_S, FOUILLER_DAILY_CAP)
        if not ok:
            await inter.response.send_message(msg, ephemeral=True)
            return

        res = fouiller_action(storage, inter.user.id)
        await inter.response.send_message(res["msg"])

    @hess.command(name="classement", description="Top 10 des joueurs les plus chargés")
    async def classement(inter: Interaction):
        storage = inter.client.storage
        try:
            rows = storage.top_richest(limit=10)  # [(user_id, money)]
        except Exception:
            rows = []

        if not rows:
            await inter.response.send_message(
                "Aucun joueur classé pour l’instant. Lance **/start** puis **/hess mendier** / **/hess fouiller**.",
                ephemeral=True
            )
            return

        desc = _format_leaderboard(rows)
        embed = discord.Embed(
            title="🏆 LaRue.exe",
            description=desc,
            color=discord.Color.dark_gold()
        )
        embed.set_footer(text="Top 10 — riche aujourd’hui, pauvre demain…")
        await inter.response.send_message(embed=embed, ephemeral=False)

    # /stats (global ou guild-scoped selon settings)
    @tree.command(name="stats", description="Tes stats")
    @app_commands.guilds(guild_obj) if guild_obj else (lambda f: f)
    async def stats(inter: Interaction):
        storage = inter.client.storage
        p = storage.get_player(inter.user.id)
        msg = stats_action(storage, inter.user.id)
        # si pas commencé, rends-le éphémère
        ephemeral = not (p and p.get("has_started"))
        await inter.response.send_message(msg, ephemeral=ephemeral)

    # Attache le groupe au tree
    if guild_obj:
        tree.add_command(hess, guild=guild_obj)
    else:
        tree.add_command(hess)

# Compat setup
def setup_economy(tree: app_commands.CommandTree, guild_obj: discord.Object | None):
    register(tree, guild_obj, None)