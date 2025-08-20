# bot/modules/rp/recycler.py
from __future__ import annotations
from typing import Optional, Tuple
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import discord
from discord import app_commands, Interaction

from bot.modules.common.money import fmt_eur

# ───────────────────────────────────────────────────────────────────
# Config recyclerie (centimes)
# ───────────────────────────────────────────────────────────────────
TZ_NAME               = "Europe/Paris"
DAY_START_HOUR        = 8                 # la "journée" démarre à 08:00 locale
BACKLOG_MAX_DAYS      = 3                 # rattrapage max
CANETTES_PAR_SAC      = 50
TAX_BP                = 500               # 5% (basis points)
STREAK_BONUS_BP       = 800               # +8%/jour de streak
STREAK_CAP_DAYS       = 7

# Valeur brute d'1 sac par niveau (L1→L3). Tu pourras en ajouter plus tard.
SAC_VALUE_BY_LEVEL = {
    1: 120,   # 1,20 €
    2: 180,   # 1,80 €
    3: 260,   # 2,60 €
}

# ───────────────────────────────────────────────────────────────────
# Petits utilitaires date/stock
# ───────────────────────────────────────────────────────────────────
def _today_key() -> int:
    """
    Renvoie un entier AAAAMMJJ basé sur un "jour" qui commence à DAY_START_HOUR dans TZ_NAME.
    """
    now = datetime.now(ZoneInfo(TZ_NAME))
    start = now.replace(hour=DAY_START_HOUR, minute=0, second=0, microsecond=0)
    if now < start:
        start -= timedelta(days=1)
    return int(start.strftime("%Y%m%d"))

def _defaults() -> dict:
    return {
        "recy_level": 1,
        "recy_canettes": 0,
        "recy_sacs": 0,
        "recy_streak": 0,
        "recy_last_day": 0,  # AAAAMMJJ (0 = jamais collecté)
    }

def _load_state(storage, uid: int) -> dict:
    prof = storage.get_profile(uid) or {}
    base = _defaults()
    for k in base:
        if k in prof:
            base[k] = prof[k]
    # types sûrs
    base["recy_level"]    = int(base["recy_level"] or 1)
    base["recy_canettes"] = int(base["recy_canettes"] or 0)
    base["recy_sacs"]     = int(base["recy_sacs"] or 0)
    base["recy_streak"]   = int(base["recy_streak"] or 0)
    base["recy_last_day"] = int(base["recy_last_day"] or 0)
    return base

def _save_state(storage, uid: int, st: dict) -> None:
    storage.upsert_profile(
        uid,
        recy_level= int(st["recy_level"]),
        recy_canettes=int(st["recy_canettes"]),
        recy_sacs=int(st["recy_sacs"]),
        recy_streak=int(st["recy_streak"]),
        recy_last_day=int(st["recy_last_day"]),
    )

def _pending_days(st: dict) -> int:
    """
    Combien de jours de claim disponibles (rattrapage compris, capped).
    """
    today = _today_key()
    last  = int(st["recy_last_day"] or 0)
    if last <= 0:
        return 1  # premier claim offert
    diff = max(0, _diff_days_key(last, today))
    return min(diff, BACKLOG_MAX_DAYS)

def _diff_days_key(d1_key: int, d2_key: int) -> int:
    # convertit AAAAMMJJ → datetime (à DAY_START_HOUR), calcule la diff
    z = ZoneInfo(TZ_NAME)
    d1 = datetime.strptime(str(d1_key), "%Y%m%d").replace(tzinfo=z, hour=DAY_START_HOUR)
    d2 = datetime.strptime(str(d2_key), "%Y%m%d").replace(tzinfo=z, hour=DAY_START_HOUR)
    return (d2 - d1).days

def _current_net_value_per_sac(level: int, streak: int) -> Tuple[int, int, int]:
    """
    Retourne (gross, tax, net) pour 1 sac au niveau donné avec le streak actuel (cap appliqué).
    """
    base = int(SAC_VALUE_BY_LEVEL.get(level, SAC_VALUE_BY_LEVEL[1]))
    eff_streak = min(max(0, streak), STREAK_CAP_DAYS)
    gross = int(round(base * (1 + (STREAK_BONUS_BP * eff_streak) / 10000)))
    tax   = int(round(gross * TAX_BP / 10000))
    net   = max(0, gross - tax)
    return gross, tax, net

# ───────────────────────────────────────────────────────────────────
# Embeds
# ───────────────────────────────────────────────────────────────────
def _embed_statut(storage, uid: int) -> discord.Embed:
    st = _load_state(storage, uid)
    today  = _today_key()
    pend   = _pending_days(st)
    gross, tax, net = _current_net_value_per_sac(st["recy_level"], st["recy_streak"])

    streak_bar = "🟩" * min(st["recy_streak"], STREAK_CAP_DAYS) + "⬛" * max(0, STREAK_CAP_DAYS - st["recy_streak"])
    e = discord.Embed(
        title="♻️ Recyclerie de canettes",
        description="Transforme **canettes** → **sacs** → **cash** chaque jour.",
        color=discord.Color.dark_teal(),
    )
    e.add_field(name="🧺 Sacs prêts", value=str(st["recy_sacs"]), inline=True)
    e.add_field(name="🥤 Canettes en vrac", value=str(st["recy_canettes"]), inline=True)
    e.add_field(name="⏳ Jours à encaisser", value=str(pend), inline=True)

    e.add_field(
        name="💰 Valeur par sac (net)",
        value=f"**{fmt_eur(net)}**  *(brut {fmt_eur(gross)} − taxe {fmt_eur(tax)})*",
        inline=False
    )
    e.add_field(
        name="🔥 Série (streak)",
        value=f"{st['recy_streak']}/{STREAK_CAP_DAYS}  {streak_bar}",
        inline=False
    )
    e.set_footer(text=f"{CANETTES_PAR_SAC} canettes = 1 sac • rattrapage max {BACKLOG_MAX_DAYS} j")
    return e

def _embed_collect_result(storage, uid: int, was_claimed: int, paid_total_cents: int, new_state: dict) -> discord.Embed:
    e = discord.Embed(
        title="✅ Collecte effectuée",
        description=f"Tu encaisses **{was_claimed}** jour(s).",
        color=discord.Color.green()
    )
    e.add_field(name="💵 Cash reçu", value=f"**{fmt_eur(paid_total_cents)}**", inline=True)
    e.add_field(name="🧺 Sacs restants", value=str(new_state["recy_sacs"]), inline=True)
    e.add_field(name="🔥 Série (streak)", value=str(new_state["recy_streak"]), inline=True)
    e.set_footer(text="Reviens demain à partir de 08:00 (heure Paris).")
    return e

def _embed_compresser_result(nb_sacs: int, canettes_consommees: int, st: dict) -> discord.Embed:
    e = discord.Embed(
        title="🧯 Compression effectuée",
        description=f"Tu as compacté **{canettes_consommees}** canettes → **{nb_sacs}** sac(s).",
        color=discord.Color.dark_gold()
    )
    e.add_field(name="🧺 Sacs totaux", value=str(st["recy_sacs"]), inline=True)
    e.add_field(name="🥤 Canettes restantes", value=str(st["recy_canettes"]), inline=True)
    e.set_footer(text=f"{CANETTES_PAR_SAC} canettes = 1 sac")
    return e

# ───────────────────────────────────────────────────────────────────
# Logic
# ───────────────────────────────────────────────────────────────────
def _ensure_started(inter: Interaction) -> bool:
    storage = inter.client.storage
    p = storage.get_player(inter.user.id)
    return bool(p and p.get("has_started"))

def _require_started(inter: Interaction) -> bool:
    if not _ensure_started(inter):
        # on garde le même wording que le reste de ton bot
        # (pas ephemeral=False ici pour éviter le bruit)
        return False
    return True

def _craft_sacs_from_canettes(st: dict, nb_souhaite: Optional[int]) -> Tuple[int, int]:
    """
    nb_souhaite=None → craft tout. Retourne (nb_sacs_craftés, canettes_consommées).
    """
    possible = st["recy_canettes"] // CANETTES_PAR_SAC
    to_make = possible if (nb_souhaite is None or nb_souhaite > possible) else max(0, int(nb_souhaite))
    if to_make <= 0:
        return 0, 0
    consume = to_make * CANETTES_PAR_SAC
    st["recy_canettes"] -= consume
    st["recy_sacs"]     += to_make
    return to_make, consume

def _claim_days(st: dict, nb: int) -> Tuple[int, int]:
    """
    Applique jusqu'à 'nb' claims (1 sac/claim, 1 jour/claim).
    Retourne (nb_claims_effectués, total_net_pay_cents).
    """
    today = _today_key()
    paid_total = 0
    done = 0

    # combien de jours dispo + limite sacs
    pend = _pending_days(st)
    nb = max(0, min(nb, pend, st["recy_sacs"]))
    if nb <= 0:
        return 0, 0

    # streak: s'il y a un trou (>1 jour), on reset d'abord
    if st["recy_last_day"] > 0:
        miss = _diff_days_key(st["recy_last_day"], today)
        if miss > 1:
            st["recy_streak"] = 0

    # on "simule" jour par jour
    cur_day = st["recy_last_day"] if st["recy_last_day"] else (today - 1)
    for _ in range(nb):
        # avancer d'un jour
        cur_day += 1
        # appliquer streak (+1 jusqu'au cap)
        st["recy_streak"] = min(STREAK_CAP_DAYS, st["recy_streak"] + 1)

        # payer ce jour
        _, _, net = _current_net_value_per_sac(st["recy_level"], st["recy_streak"])
        paid_total += net
        st["recy_sacs"] = max(0, st["recy_sacs"] - 1)
        done += 1

    st["recy_last_day"] = today
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

        st = _load_state(storage, inter.user.id)
        made, consumed = _craft_sacs_from_canettes(st, sacs)
        if made <= 0:
            await inter.response.send_message("🙃 Pas assez de canettes pour faire un sac.", ephemeral=True)
            return

        _save_state(storage, inter.user.id, st)
        await inter.response.send_message(embed=_embed_compresser_result(made, consumed, st))

    @group.command(name="collecter", description="Encaisser (1 sac par jour disponible, rattrapage limité)")
    @app_commands.describe(nb="Nombre de jours à encaisser (par défaut: 1)")
    async def collecter(inter: Interaction, nb: Optional[int] = 1):
        storage = inter.client.storage
        if not _require_started(inter):
            await inter.response.send_message("🚀 Lance **/start** pour déverrouiller la recyclerie.", ephemeral=True)
            return

        st = _load_state(storage, inter.user.id)
        nb = 1 if (nb is None or nb <= 0) else int(nb)

        done, paid = _claim_days(st, nb)
        if done <= 0:
            # Feedback précis
            if st["recy_sacs"] <= 0:
                msg = "🧺 Tu n’as pas de sac prêt."
            elif _pending_days(st) <= 0:
                msg = "⏳ Rien à encaisser pour l’instant. Reviens après 08:00."
            else:
                msg = "😶 Rien à faire."
            await inter.response.send_message(msg, ephemeral=True)
            return

        # crédit monnaie
        if hasattr(storage, "add_money"):
            storage.add_money(inter.user.id, paid)
        else:
            p = storage.get_player(inter.user.id)
            storage.update_player(inter.user.id, money=int(p["money"]) + paid)

        _save_state(storage, inter.user.id, st)
        await inter.response.send_message(embed=_embed_collect_result(storage, inter.user.id, done, paid, st))

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
    Avec une proba 'prob', ajoute aléatoirement des canettes (roll_min..roll_max) au profil.
    Retourne le nombre ajouté (0 si rien).
    Appelle-la juste après ta résolution de fouiller().
    """
    import random
    if random.random() > max(0.0, min(1.0, prob)):
        return 0
    add = random.randint(int(roll_min), int(roll_max))
    st = _load_state(storage, user_id)
    st["recy_canettes"] += add
    _save_state(storage, user_id, st)
    return add