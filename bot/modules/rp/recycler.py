# bot/modules/rp/recycler.py
from __future__ import annotations
from typing import Optional, Tuple
from datetime import datetime, UTC, timedelta
from zoneinfo import ZoneInfo
import time

import discord
from discord import app_commands, Interaction

from bot.modules.common.money import fmt_eur
from bot.modules.rp.boosts import compute_power


# ───────────────────────────────────────────────────────────────────
# Config recyclerie (centimes)
# ───────────────────────────────────────────────────────────────────
TZ_NAME               = "Europe/Paris"
DAY_START_HOUR        = 8                 # la "journée" démarre à 08:00 locale
BACKLOG_MAX_DAYS      = 3                 # rattrapage max
CANETTES_PAR_SAC      = 50
STREAK_BONUS_BP       = 800               # +8%/jour de streak
STREAK_CAP_DAYS       = 7

# Valeur de base d'1 sac par niveau (L1→L3). Tu pourras en ajouter plus tard.
SAC_VALUE_BY_LEVEL = {
    1: 120,   # 1,20 €
    2: 180,   # 1,80 €
    3: 260,   # 2,60 €
}

# ───────────────────────────────────────────────────────────────────
# Dates / reset (style economy)
# ───────────────────────────────────────────────────────────────────
def _today_key() -> int:
    """Entier AAAAMMJJ basé sur un 'jour' qui commence à DAY_START_HOUR dans TZ_NAME."""
    now = datetime.now(ZoneInfo(TZ_NAME))
    start = now.replace(hour=DAY_START_HOUR, minute=0, second=0, microsecond=0)
    if now < start:
        start -= timedelta(days=1)
    return int(start.strftime("%Y%m%d"))

def _reset_window_epochs(tz_name: str = TZ_NAME, hour: int = DAY_START_HOUR) -> tuple[int, int]:
    """
    Renvoie (start_epoch_utc, next_epoch_utc) pour la fenêtre quotidienne courante.
    Début à hour:00 locale, fin le lendemain à la même heure.
    """
    now_local = datetime.now(ZoneInfo(tz_name))
    start_local = now_local.replace(hour=hour, minute=0, second=0, microsecond=0)
    if now_local < start_local:
        start_local -= timedelta(days=1)
    next_local = start_local + timedelta(days=1)
    return (
        int(start_local.astimezone(UTC).timestamp()),
        int(next_local.astimezone(UTC).timestamp())
    )

def _next_reset_epoch(tz_name: str = TZ_NAME, hour: int = DAY_START_HOUR) -> int:
    """Prochain reset quotidien (epoch UTC)."""
    _, nxt = _reset_window_epochs(tz_name, hour)
    return nxt

def _diff_days_key(d1_key: int, d2_key: int) -> int:
    z = ZoneInfo(TZ_NAME)
    d1 = datetime.strptime(str(d1_key), "%Y%m%d").replace(tzinfo=z, hour=DAY_START_HOUR)
    d2 = datetime.strptime(str(d2_key), "%Y%m%d").replace(tzinfo=z, hour=DAY_START_HOUR)
    return (d2 - d1).days

def _pending_days(state: dict) -> int:
    """Combien de jours de claim disponibles (rattrapage compris, capped)."""
    today = _today_key()
    last  = int(state["last_day"] or 0)
    if last <= 0:
        return 1  # premier claim offert
    diff = max(0, _diff_days_key(last, today))
    return min(diff, BACKLOG_MAX_DAYS)

# ───────────────────────────────────────────────────────────────────
# UI helpers (progress/cooldown style economy)
# ───────────────────────────────────────────────────────────────────
def _progress_bar(elapsed: int, total: int, width: int = 10) -> tuple[str, int]:
    if total <= 0:
        return "──────────", 100
    pct = max(0.0, min(1.0, elapsed / total))
    filled = int(round(pct * width))
    return "█" * filled + "─" * (width - filled), int(pct * 100)

def _reset_field() -> tuple[str, str]:
    """
    Renvoie (titre, valeur) pour un champ 'Prochain reset', avec barre de progression
    entre le début de la fenêtre courante (08:00) et le prochain reset.
    """
    start_ep, next_ep = _reset_window_epochs()
    now = int(time.time())
    elapsed = max(0, now - start_ep)
    total   = max(1, next_ep - start_ep)
    bar, pct = _progress_bar(elapsed, total)
    val = f"⏳ Prêt {f'<t:{next_ep}:R>'} • <t:{next_ep}:T>\n`{bar}` {pct}%"
    return "🕗 Prochain reset", val

# ───────────────────────────────────────────────────────────────────
# Valeur des sacs (UX simplifiée)
# ───────────────────────────────────────────────────────────────────
def _value_per_sac(level: int, streak: int) -> int:
    """Valeur NETTE d'un sac : base × (1 + bonus_streak)."""
    base = int(SAC_VALUE_BY_LEVEL.get(level, SAC_VALUE_BY_LEVEL[1]))
    eff = min(max(0, streak), STREAK_CAP_DAYS)
    return int(round(base * (1 + (STREAK_BONUS_BP * eff) / 10000)))

# ───────────────────────────────────────────────────────────────────
# Embeds
# ───────────────────────────────────────────────────────────────────
def _embed_statut(storage, uid: int) -> discord.Embed:
    st = storage.get_recycler_state(uid)
    pend = _pending_days(st)
    per_sac = _value_per_sac(st["level"], st["streak"])
    bonus_pct = int((STREAK_BONUS_BP * min(st["streak"], STREAK_CAP_DAYS)) / 100)  # en %

    streak_bar = "🟩" * min(st["streak"], STREAK_CAP_DAYS) + "⬛" * max(0, STREAK_CAP_DAYS - st["streak"])
    e = discord.Embed(
        title="♻️ Recyclerie de canettes",
        description=(
            "Chaque jour : **1 encaissement** (consomme **1 sac**)."
        ),
        color=discord.Color.dark_teal(),
    )
    e.add_field(name="🧺 Sacs prêts",        value=str(st["sacs"]),     inline=True)
    e.add_field(name="🥤 Canettes en vrac",  value=str(st["canettes"]), inline=True)
    e.add_field(name="⏳ Jours à encaisser", value=str(pend), inline=True)

    e.add_field(
        name="💰 Valeur par sac",
        value=f"**{fmt_eur(per_sac)}**  *(bonus série : +{bonus_pct}%)*",
        inline=False
    )
    e.add_field(
        name="🔥 Série (streak)",
        value=f"**{st['streak']} / {STREAK_CAP_DAYS}**  {streak_bar}",
        inline=False
    )

    e.set_footer(text=f"{CANETTES_PAR_SAC} canettes = 1 sac • rattrapage max {BACKLOG_MAX_DAYS} j • reset 08:00")
    return e

def _embed_collect_result(was_claimed: int, paid_total_cents: int, new_state: dict) -> discord.Embed:
    e = discord.Embed(
        title="✅ Collecte effectuée",
        description=f"Tu encaisses **{was_claimed}** jour(s).",
        color=discord.Color.green()
    )
    e.add_field(name="💵 Cash reçu",      value=f"**{fmt_eur(paid_total_cents)}**", inline=True)
    e.add_field(name="🧺 Sacs restants",  value=str(new_state["sacs"]),             inline=True)
    e.add_field(name="🔥 Série (streak)", value=str(new_state["streak"]),           inline=True)
    e.set_footer(text="Reviens demain (après 08:00, heure Paris) pour garder ta série.")
    return e

def _embed_compresser_result(nb_sacs: int, canettes_consommees: int, st: dict) -> discord.Embed:
    e = discord.Embed(
        title="🧯 Compression effectuée",
        description=f"Tu as compacté **{canettes_consommees}** canettes → **{nb_sacs}** sac(s).",
        color=discord.Color.dark_gold()
    )
    e.add_field(name="🧺 Sacs totaux",         value=str(st["sacs"]),     inline=True)
    e.add_field(name="🥤 Canettes restantes",  value=str(st["canettes"]), inline=True)
    e.set_footer(text=f"{CANETTES_PAR_SAC} canettes = 1 sac")
    return e

def _embed_wait_reset(st: dict) -> discord.Embed:
    """Embed affiché quand on essaie de collecter trop tôt (avant le reset)."""
    e = discord.Embed(
        title="⏳ Trop tôt pour encaisser",
        description="La caisse rouvre chaque jour à **08:00** (heure Paris).",
        color=discord.Color.dark_grey()
    )
    name, val = _reset_field()
    e.add_field(name=name, value=val, inline=False)
    e.add_field(name="🧺 Sacs prêts", value=str(st["sacs"]), inline=True)
    return e

# ───────────────────────────────────────────────────────────────────
# Logic helpers
# ───────────────────────────────────────────────────────────────────
def _ensure_started(inter: Interaction) -> bool:
    storage = inter.client.storage
    p = storage.get_player(inter.user.id)
    return bool(p and p.get("has_started"))

def _require_started(inter: Interaction) -> bool:
    return _ensure_started(inter)

def _craft_sacs_from_canettes(state: dict, nb_souhaite: Optional[int]) -> Tuple[int, int]:
    """
    nb_souhaite=None → craft tout. Retourne (nb_sacs_craftés, canettes_consommées).
    """
    possible = state["canettes"] // CANETTES_PAR_SAC
    to_make = possible if (nb_souhaite is None or nb_souhaite > possible) else max(0, int(nb_souhaite))
    if to_make <= 0:
        return 0, 0
    consume = to_make * CANETTES_PAR_SAC
    state["canettes"] -= consume
    state["sacs"]     += to_make
    return to_make, consume

def _claim_days(storage, uid: int, state: dict, nb: int) -> Tuple[int, int]:
    """
    Encaisse jusqu'à 'nb' jours (1 sac/claim).
    Paie avec le streak ACTUEL, puis incrémente.
    Log dans recycler_claims (gross=net, tax=0).
    """
    today = _today_key()
    paid_total = 0
    done = 0

    pend = _pending_days(state)
    nb = max(0, min(nb, pend, state["sacs"]))
    if nb <= 0:
        return 0, 0

    # reset streak si trou > 1 jour
    if state["last_day"] > 0:
        miss = _diff_days_key(state["last_day"], today)
        if miss > 1:
            state["streak"] = 0

    cur_day = state["last_day"] if state["last_day"] else (today - 1)
    for _ in range(nb):
        cur_day += 1

        # payer avec le streak courant
        net = _value_per_sac(state["level"], state["streak"])
        paid_total += net
        state["sacs"] = max(0, state["sacs"] - 1)
        done += 1

        if hasattr(storage, "log_recycler_claim"):
            storage.log_recycler_claim(uid, cur_day, 1, net, 0, net)

        # incrémenter pour le prochain jour
        state["streak"] = min(STREAK_CAP_DAYS, state["streak"] + 1)

    state["last_day"] = today
    return done, paid_total

# ───────────────────────────────────────────────────────────────────
# Slash commands
# ───────────────────────────────────────────────────────────────────
def register(tree: app_commands.CommandTree, guild_obj: Optional[discord.Object], client: discord.Client | None = None):
    group = app_commands.Group(name="recycler", description="Recyclerie de canettes (revenu passif)")

    @group.command(name="statut", description="Voir ton état: canettes, sacs, valeur, série…")
    async def statut(inter: Interaction):
        storage = inter.client.storage
        if not _require_started(inter):
            await inter.response.send_message("🚀 Lance **/start** pour déverrouiller la recyclerie.", ephemeral=True)
            return
        await inter.response.send_message(embed=_embed_statut(storage, inter.user.id))

    @group.command(name="compresser", description="Compacter tes canettes en sacs prêts à revendre")
    @app_commands.describe(sacs="Nombre de sacs à fabriquer (laisse vide = tout)")
    async def compresser(inter: Interaction, sacs: Optional[int] = None):
        storage = inter.client.storage
        if not _require_started(inter):
            await inter.response.send_message("🚀 Lance **/start** pour déverrouiller la recyclerie.", ephemeral=True)
            return

        st = storage.get_recycler_state(inter.user.id)
        made, consumed = _craft_sacs_from_canettes(st, sacs)
        if made <= 0:
            await inter.response.send_message("🙃 Pas assez de canettes pour faire un sac.", ephemeral=True)
            return

        storage.update_recycler_state(inter.user.id, **st)
        await inter.response.send_message(embed=_embed_compresser_result(made, consumed, st))

    @group.command(name="collecter", description="Encaisser (1 jour dispo = 1 sac consommé)")
    @app_commands.describe(nb="Nombre de jours à encaisser (défaut: 1)")
    async def collecter(inter: Interaction, nb: Optional[int] = 1):
        storage = inter.client.storage
        if not _require_started(inter):
            await inter.response.send_message("🚀 Lance **/start** pour déverrouiller la recyclerie.", ephemeral=True)
            return

        st = storage.get_recycler_state(inter.user.id)
        nb = 1 if (nb is None or nb <= 0) else int(nb)

        done, paid = _claim_days(storage, inter.user.id, st, nb)
        if done <= 0:
            if st["sacs"] <= 0:
                await inter.response.send_message("🧺 Tu n’as pas de sac prêt.", ephemeral=True)
                return
            if _pending_days(st) <= 0:
                await inter.response.send_message(embed=_embed_wait_reset(st), ephemeral=True)
                return
            await inter.response.send_message("😶 Rien à faire.", ephemeral=True)
            return

        # crédit monnaie
        if hasattr(storage, "add_money"):
            storage.add_money(inter.user.id, paid)
        else:
            p = storage.get_player(inter.user.id)
            storage.update_player(inter.user.id, money=int(p["money"]) + paid)

        storage.update_recycler_state(inter.user.id, **st)
        await inter.response.send_message(embed=_embed_collect_result(done, paid, st))

    # Enregistre le groupe
    if guild_obj:
        tree.add_command(group, guild=guild_obj)
    else:
        tree.add_command(group)

# ───────────────────────────────────────────────────────────────────
# Hook optionnel à appeler depuis /hess fouiller pour “drop” des canettes
# ───────────────────────────────────────────────────────────────────
def maybe_grant_canettes_after_fouiller(storage, user_id: int, *, prob: float = 0.6, roll_min: int = 8, roll_max: int = 20) -> int:
    """
    Avec une proba 'prob', ajoute aléatoirement des canettes (roll_min..roll_max) au state recyclerie.
    Retourne le nombre ajouté (0 si rien).
    Appelle-la juste après ta résolution de fouiller().
    """
    import random
    power = compute_power(storage, user_id) if callable(compute_power) else {}

    prob_mult = float(power.get("recy_canette_prob_mult", 1.0))
    roll_bonus = int(power.get("recy_canette_roll_bonus", 0))

    eff_prob = max(0.0, min(0.99, prob * prob_mult))
    if random.random() > eff_prob:
        return 0

    add = random.randint(int(roll_min), int(roll_max)) + max(0, roll_bonus)

    if hasattr(storage, "add_recycler_canettes"):
        storage.add_recycler_canettes(user_id, add)
    else:
        st = storage.get_recycler_state(user_id)
        st["canettes"] += add
        storage.update_recycler_state(user_id, **st)
    return add