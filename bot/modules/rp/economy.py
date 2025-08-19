from __future__ import annotations
import asyncio
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

# --- UI helpers (embeds & mini-anim) ---
def _now_ts() -> int:
    return int(time.time())

def _cooldown_field(storage, user_id: int, action: str, cd: int, cap: int) -> tuple[str, str]:
    """
    Retourne (titre, valeur) pour un champ 'Cooldown' homogène avec barre de progression.
    """
    last_ts = 0
    remaining = None
    if hasattr(storage, "get_action_state"):
        st = storage.get_action_state(user_id, action)
        last_ts = int(st.get("last_ts", 0) or 0)
        remaining = st.get("remaining", None)

    now = _now_ts()
    elapsed = max(0, now - last_ts)
    bar, pct = _progress_bar(elapsed, max(cd, 1))

    if elapsed < cd and last_ts > 0:
        available_at = last_ts + cd
        suffix = f"(reste **{remaining}**)" if isinstance(remaining, int) and remaining >= 0 else ""
        val = f"⏳ Prêt {f'<t:{available_at}:R>'} • <t:{available_at}:T> {suffix}\n`{bar}` {pct}%"
    else:
        suffix = f"(reste **{remaining}**)" if isinstance(remaining, int) and remaining >= 0 else ""
        val = f"✅ Disponible {suffix}\n`{bar}` 100%"
    return ("⏱️ Cooldown", val)

def _result_embed(
    *,
    title: str,
    icon: str,
    flavor: str,
    delta_cents: int,
    total_cents: int,
    color: discord.Color,
    storage,
    user_id: int,
    action_key: str,
    cooldown_s: int,
    cap: int,
) -> discord.Embed:
    gain = fmt_eur(delta_cents)
    total = fmt_eur(total_cents)

    e = discord.Embed(
        title=f"{icon}  {title}",
        description=flavor,
        color=color
    )
    e.add_field(name="💸 Gain", value=f"**{('+' if delta_cents>0 else '')}{gain}**", inline=True)
    e.add_field(name="💼 Capital", value=f"**{total}**", inline=True)

    name, val = _cooldown_field(storage, user_id, action_key, cooldown_s, cap)
    e.add_field(name=name, value=val, inline=False)
    e.set_footer(text="LaRue.exe • Reste poli, ça paye parfois.")
    return e

async def _play_anim_then_finalize(
    inter: Interaction,
    *,
    title: str,
    pre_lines: list[str],
    color: discord.Color,
    final_embed: discord.Embed,
    delay: float = 0.6
):
    """
    Envoie un embed 'en cours…' puis le met à jour 1-2 fois avant le résultat.
    """
    # 1) premier écran
    anim = discord.Embed(title=title, description=pre_lines[0], color=color)
    await inter.response.send_message(embed=anim)
    msg = await inter.original_response()

    # 2) steps optionnels
    for line in pre_lines[1:]:
        await asyncio.sleep(delay)
        anim.description = line
        await msg.edit(embed=anim)

    # 3) résultat
    await asyncio.sleep(delay)
    await msg.edit(embed=final_embed)

# ───────── Actions réutilisables (centimes) ─────────
def mendier_action(storage, user_id: int) -> dict:
    """Gain faible, boostable par l’inventaire. Incrémente le compteur d’usage."""
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

    # Argent
    if hasattr(storage, "add_money"):
        pp = storage.add_money(user_id, amount)
    else:
        pp = storage.update_player(user_id, money=p["money"] + amount)

    # Stat d’usage (pour déblocages par paliers)
    if hasattr(storage, "increment_stat"):
        storage.increment_stat(user_id, "mendier_count", 1)

    return {
        "money": pp["money"],
        "delta": amount,
        "msg": f"Tu tends la main… +{fmt_eur(amount)} • Total {fmt_eur(pp['money'])}",
    }

def fouiller_action(storage, user_id: int) -> dict:
    """Issue “bon / rien / perte”, légèrement boostée par inventaire. Incrémente le compteur d’usage."""
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

        msg = {"money": pp["money"], "delta": gain, "msg": f"Tu revends des trucs: +{fmt_eur(gain)} • Total {fmt_eur(pp['money'])}"}

    elif r < 0.9:
        # Rien trouvé (mais l’action compte tout de même pour l’XP/déblocage)
        msg = {"money": p["money"], "delta": 0, "msg": "Rien d’intéressant."}

    else:
        perte = min(FOUILLER_BAD_LOSS, p["money"])
        pp = storage.update_player(user_id, money=max(0, p["money"] - perte))
        msg = {"money": pp["money"], "delta": -perte, "msg": f"Tu te fais gratter. -{fmt_eur(perte)} • Total {fmt_eur(pp['money'])}"}

    # Stat d’usage (on compte chaque fouille autorisée)
    if hasattr(storage, "increment_stat"):
        storage.increment_stat(user_id, "fouiller_count", 1)

    return msg

def poches_action(storage, user_id: int) -> discord.Embed:
    money_cents = storage.get_money(user_id)
    embed = discord.Embed(
        description=f"En fouillant un peu, t’arrives à racler : **{fmt_eur(money_cents)}**",
        color=discord.Color.dark_gold()
    )
    return embed

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

        # Calcul du résultat (crédit immédiat)
        res = mendier_action(storage, inter.user.id)

        flavor_lines = [
            "🤲 Tu te poses au feu rouge…",
            "👀 Un passant fouille sa poche…",
            "💸 Une pièce glisse dans ta main.",
        ]
        final_embed = _result_embed(
            title="Mendier",
            icon="🥖",
            flavor="« Merci chef… la rue te sourit un peu aujourd’hui. »",
            delta_cents=res["delta"],
            total_cents=res["money"],
            color=discord.Color.blurple(),
            storage=storage,
            user_id=inter.user.id,
            action_key="mendier",
            cooldown_s=MENDIER_COOLDOWN_S,
            cap=MENDIER_DAILY_CAP,
        )

        await _play_anim_then_finalize(
            inter,
            title="🥖 Mendier",
            pre_lines=flavor_lines,
            color=discord.Color.blurple(),
            final_embed=final_embed,
            delay=0.6
        )

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

        # Saveur selon issue
        if res["delta"] > 0:
            flavor = "🧳 Entre canettes et cartons… un truc revendable !"
            color = discord.Color.green()
        elif res["delta"] == 0:
            flavor = "🗑️ Bruit, odeur, rats… et rien au fond."
            color = discord.Color.gold()
        else:
            flavor = "🙄 Mauvaise rencontre. Le trottoir t’a coûté des sous."
            color = discord.Color.red()

        anim_lines = [
            "♻️ Tu soulèves le couvercle…",
            "🔦 Tu éclaires tout au fond…",
            "🫳 Tu tires quelque chose…",
        ]
        final_embed = _result_embed(
            title="Fouiller",
            icon="🗑️",
            flavor=flavor,
            delta_cents=res["delta"],
            total_cents=res["money"],
            color=color,
            storage=storage,
            user_id=inter.user.id,
            action_key="fouiller",
            cooldown_s=FOUILLER_COOLDOWN_S,
            cap=FOUILLER_DAILY_CAP,
        )

        await _play_anim_then_finalize(
            inter,
            title="🗑️ Fouiller",
            pre_lines=anim_lines,
            color=color,
            final_embed=final_embed,
            delay=0.6
        )

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

    @tree.command(name="poches", description="Check ce qu’il te reste dans les poches")
    @app_commands.guilds(guild_obj) if guild_obj else (lambda f: f)
    async def poches(inter: Interaction):
        storage = inter.client.storage
        p = storage.get_player(inter.user.id)
        embed = poches_action(storage, inter.user.id)  # ← construit l'embed
        await inter.response.send_message(embed=embed, ephemeral=not (p and p.get("has_started")))

    if guild_obj:
        tree.add_command(hess, guild=guild_obj)
    else:
        tree.add_command(hess)

# Compat setup
def setup_economy(tree: app_commands.CommandTree, guild_obj: discord.Object | None):
    register(tree, guild_obj, None)

check_limit = _check_limit