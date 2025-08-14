from __future__ import annotations
import random, time
from datetime import datetime, UTC, timedelta
import discord
from discord import app_commands, Interaction
from zoneinfo import ZoneInfo

from bot.modules.rp.boosts import compute_power
from bot.modules.common.money import fmt_eur

# ───────── Équilibrage (centimes) ─────────
MENDIER_COOLDOWN_S  = 60 * 60         # 1h
FOUILLER_COOLDOWN_S = 60 * 60 * 24    # 24h
MENDIER_DAILY_CAP   = 10              # 10/jour
FOUILLER_DAILY_CAP  = 1               # 1/jour

# Gains/pertes (centimes)
MENDIER_MIN_CENTS = 5      # 0,05€
MENDIER_MAX_CENTS = 80     # 0,80€

FOUILLER_GOOD_MIN = 50     # 0,50€
FOUILLER_GOOD_MAX = 300    # 3,00€
FOUILLER_BAD_LOSS = 100    # -1,00€ max

# Messages “limite du jour” par action
DAILY_LIMIT_MSGS = {
    "mendier":  "⛔ Plus une pièce à gratter aujourd’hui. Reset {reset_rel} • {reset_time}",
    "fouiller": "⛔ Plus un coin de poubelle à fouiller aujourd’hui. Reset {reset_rel} • {reset_time}",
}

# ───────── Utils (classement + cooldown UX) ─────────
def _medal(i: int) -> str:
    return "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🏅"

def _format_leaderboard(rows: list[tuple[str | int, int]]) -> str:
    """rows: [(user_id, money_cents), ...]"""
    lines: list[str] = []
    for i, (uid, cents) in enumerate(rows, start=1):
        mention = f"<@{int(uid)}>"  # pas de ping dans un embed
        lines.append(f"**{i:>2}.** {mention} — **{fmt_eur(cents)}** {_medal(i)}")
    return "\n".join(lines)

def _progress_bar(elapsed: int, total: int, width: int = 10) -> tuple[str, int]:
    if total <= 0:
        return "──────────", 100
    pct = max(0.0, min(1.0, elapsed / total))
    filled = int(round(pct * width))
    return "█" * filled + "─" * (width - filled), int(pct * 100)

def _next_reset_epoch(tz_name: str = "Europe/Paris", hour: int = 8) -> int:
    """Prochaine coupure journalière à hour:00 (local tz), renvoyée en epoch UTC."""
    now_local = datetime.now(ZoneInfo(tz_name))
    target = now_local.replace(hour=hour, minute=0, second=0, microsecond=0)
    if now_local >= target:
        target += timedelta(days=1)
    return int(target.astimezone(UTC).timestamp())

def _cooldown_message(storage, user_id: int, action: str, wait: int, remaining: int, total_cd: int) -> str:
    """Message plus parlant pour un cooldown en cours (timestamps + barre)."""
    now = int(time.time())
    available_at = now + int(wait)

    last_ts = 0
    if hasattr(storage, "get_action_state"):
        st = storage.get_action_state(user_id, action)
        last_ts = int(st.get("last_ts", 0) or 0)

    if last_ts:
        bar, pct = _progress_bar(max(0, now - last_ts), max(total_cd, 1))
        prog = f"`{bar}` {pct}%"
    else:
        prog = "`──────────` 0%"

    rel = f"<t:{available_at}:R>"   # ex: “dans 5 heures”
    abs_t = f"<t:{available_at}:T>" # ex: “14:37”
    suffix = f"(reste **{remaining}** fois aujourd’hui)" if remaining > 0 else ""
    return f"⏳ Calme-toi. Prochaine tentative {rel} • {abs_t} {suffix}\n{prog}"

def _daily_cap_message(action: str) -> str:
    reset_at = _next_reset_epoch("Europe/Paris", 8)
    base = DAILY_LIMIT_MSGS.get(action, "⛔ Tu as atteint ta limite quotidienne.")
    return base.format(reset_rel=f"<t:{reset_at}:R>", reset_time=f"<t:{reset_at}:T>")

def _check_limit(storage, user_id: int, action: str, cd: int, cap: int) -> tuple[bool, str | None]:
    """Retourne (ok, message_si_refus). Si storage n'a pas la méthode -> toujours OK."""
    if not hasattr(storage, "check_and_touch_action"):
        return True, None
    ok, wait, remaining = storage.check_and_touch_action(user_id, action, cd, cap)
    if ok:
        return True, None
    if remaining == 0:
        return False, _daily_cap_message(action)
    return False, _cooldown_message(storage, user_id, action, wait, remaining, cd)

# ───────── Actions réutilisables (centimes) ─────────
def mendier_action(storage, user_id: int) -> dict:
    """Gain faible, boostable par l’inventaire."""
    p = storage.get_player(user_id)

    # Tirage de base en centimes
    base = random.randint(MENDIER_MIN_CENTS, MENDIER_MAX_CENTS)

    # Boosts (définis par compute_power)
    power = compute_power(storage, user_id)  # ex: {"mendier_flat_min": 10, "mendier_flat_max": 30, "mendier_mult": 1.1}
    flat_min = int(power.get("mendier_flat_min", 0))
    flat_max = int(power.get("mendier_flat_max", 0))
    flat = random.randint(flat_min, max(flat_min, flat_max)) if flat_max > 0 else 0
    mult = float(power.get("mendier_mult", 1.0))

    amount = max(1, int(round((base + flat) * mult)))

    if hasattr(storage, "add_money"):
        pp = storage.add_money(user_id, amount)
    else:
        pp = storage.update_player(user_id, money=p["money"] + amount)

    return {
        "money": pp["money"],
        "delta": amount,
        "msg": f"Tu tends la main… +{fmt_eur(amount)} • Total {fmt_eur(pp['money'])}",
    }

def fouiller_action(storage, user_id: int) -> dict:
    """Issue “bon / rien / perte”, légèrement boostée par inventaire."""
    p = storage.get_player(user_id)

    power = compute_power(storage, user_id)
    mult = float(power.get("fouiller_mult", 1.0))

    r = random.random()
    if r < 0.6:
        gain = int(round(random.randint(FOUILLER_GOOD_MIN, FOUILLER_GOOD_MAX) * mult))
        if hasattr(storage, "add_money"):
            pp = storage.add_money(user_id, gain)
        else:
            pp = storage.update_player(user_id, money=p["money"] + gain)
        return {"money": pp["money"], "delta": gain, "msg": f"Tu revends des trucs: +{fmt_eur(gain)} • Total {fmt_eur(pp['money'])}"}
    elif r < 0.9:
        return {"money": p["money"], "delta": 0, "msg": "Rien d’intéressant."}
    else:
        perte = min(FOUILLER_BAD_LOSS, p["money"])
        pp = storage.update_player(user_id, money=max(0, p["money"] - perte))
        return {"money": pp["money"], "delta": -perte, "msg": f"Tu te fais gratter. -{fmt_eur(perte)} • Total {fmt_eur(pp['money'])}"}

def stats_action(storage, user_id: int) -> str:
    p = storage.get_player(user_id)
    if not p or not p.get("has_started"):
        return "🚀 Tu n'as pas encore commencé ton aventure. Utilise **/start** pour débuter !"
    return f"💼 Argent: {fmt_eur(p['money'])}"

# ───────── Slash ─────────
def _build_group() -> app_commands.Group:
    return app_commands.Group(
        name="hess",
        description="La débrouille: mendier, fouiller, survivre."
    )

def register(tree: app_commands.CommandTree, guild_obj: discord.Object | None, client: discord.Client | None = None):
    hess = _build_group()

    @hess.command(name="mendier", description="Gagne quelques centimes (boosté par ton inventaire)")
    async def mendier(inter: Interaction):
        storage = inter.client.storage
        if not storage.get_player(inter.user.id).get("has_started"):
            await inter.response.send_message("Utilise /start avant.", ephemeral=True)
            return

        ok, msg = _check_limit(storage, inter.user.id, "mendier", MENDIER_COOLDOWN_S, MENDIER_DAILY_CAP)
        if not ok:
            await inter.response.send_message(msg, ephemeral=True)
            return

        res = mendier_action(storage, inter.user.id)
        await inter.response.send_message(res["msg"])

    @hess.command(name="fouiller", description="Fouille une poubelle (boost léger via inventaire)")
    async def fouiller(inter: Interaction):
        storage = inter.client.storage
        if not storage.get_player(inter.user.id).get("has_started"):
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
        rows = storage.top_richest(limit=10) if hasattr(storage, "top_richest") else []
        if not rows:
            await inter.response.send_message(
                "Aucun joueur classé pour l’instant. Fais **/start** puis **/hess mendier**.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🏆 LaRue.exe",
            description=_format_leaderboard(rows),
            color=discord.Color.dark_gold()
        )
        embed.set_footer(text="Top 10 — riche aujourd’hui, pauvre demain…")
        await inter.response.send_message(embed=embed, ephemeral=False)

    @tree.command(name="stats", description="Tes stats")
    @app_commands.guilds(guild_obj) if guild_obj else (lambda f: f)
    async def stats(inter: Interaction):
        storage = inter.client.storage
        p = storage.get_player(inter.user.id)
        await inter.response.send_message(
            stats_action(storage, inter.user.id),
            ephemeral=not (p and p.get("has_started"))
        )

    if guild_obj:
        tree.add_command(hess, guild=guild_obj)
    else:
        tree.add_command(hess)

# Compat setup
def setup_economy(tree: app_commands.CommandTree, guild_obj: discord.Object | None):
    register(tree, guild_obj, None)