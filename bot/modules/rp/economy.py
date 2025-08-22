# bot/modules/rp/economy.py
from __future__ import annotations
import asyncio
import random, time
from datetime import datetime, UTC, timedelta
import discord
from discord import app_commands, Interaction
from zoneinfo import ZoneInfo

from bot.modules.rp.boosts import compute_power
from bot.modules.common.money import fmt_eur
from bot.domain.economy import credit_once, debit_once, balance as ledger_balance
from bot.core.config import settings
from bot.domain.economy import balance
from bot.persistence.ledger import sum_balance as _sum_ledger


# ── NEW: hook recyclerie (no-op si absent)
try:
    from bot.modules.rp.recycler import maybe_grant_canettes_after_fouiller
except Exception:
    def maybe_grant_canettes_after_fouiller(storage, user_id: int, prob: float = 0.6, roll_min: int = 8, roll_max: int = 20) -> int:
        return 0

# ───────── Équilibrage (centimes) ─────────
MENDIER_COOLDOWN_S  = 60 * 15         # 1h
FOUILLER_COOLDOWN_S = 60 * 60     # 24h
MENDIER_DAILY_CAP   = 10              # 10/jour
FOUILLER_DAILY_CAP  = 5               # 1/jour

# Gains/pertes (centimes)
MENDIER_MIN_CENTS = 5      # 0,05€
MENDIER_MAX_CENTS = 100     # 0,80€
FOUILLER_GOOD_MIN = 50     # 0,50€
FOUILLER_GOOD_MAX = 300    # 3,00€
FOUILLER_BAD_LOSS = 100    # -1,00€ max

# Messages “limite du jour” par action
DAILY_LIMIT_MSGS = {
    "mendier":  "⛔ Plus une pièce à gratter aujourd’hui. Reset {reset_rel} • {reset_time}",
    "fouiller": "⛔ Plus un coin de poubelle à fouiller aujourd’hui. Reset {reset_rel} • {reset_time}",
}

# ───────── Utils (classement + cooldown UX) ─────────

def _fmt_delta(delta_cents: int) -> str:
    # Un seul signe, et fmt_eur ne reçoit que la valeur absolue
    amount = fmt_eur(abs(delta_cents))
    if delta_cents > 0:
        return f"+{amount}"
    if delta_cents < 0:
        return f"-{amount}"
    return amount

def _medal(i: int) -> str:
    return "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🏅"

def _format_leaderboard(rows: list[tuple[str | int, int]]) -> str:
    lines: list[str] = []
    for i, (uid, cents) in enumerate(rows, start=1):
        mention = f"<@{int(uid)}>"
        lines.append(f"**{i:>2}.** {mention} — **{fmt_eur(cents)}** {_medal(i)}")
    return "\n".join(lines)

def _progress_bar(elapsed: int, total: int, width: int = 10) -> tuple[str, int]:
    if total <= 0:
        return "──────────", 100
    pct = max(0.0, min(1.0, elapsed / total))
    filled = int(round(pct * width))
    return "█" * filled + "─" * (width - filled), int(pct * 100)

def _next_reset_epoch(tz_name: str = "Europe/Paris", hour: int = 8) -> int:
    now_local = datetime.now(ZoneInfo(tz_name))
    target = now_local.replace(hour=hour, minute=0, second=0, microsecond=0)
    if now_local >= target:
        target += timedelta(days=1)
    return int(target.astimezone(UTC).timestamp())

def _cooldown_message(storage, user_id: int, action: str, wait: int, remaining: int, total_cd: int) -> str:
    now = int(time.time())
    available_at = now + int(wait)
    last_ts = 0
    if hasattr(storage, "get_action_state"):
        st = storage.get_action_state(user_id, action)
        last_ts = int(st.get("last_ts", 0) or 0)
        remaining = st.get("remaining", remaining)
    if last_ts:
        bar, pct = _progress_bar(max(0, now - last_ts), max(total_cd, 1))
        prog = f"`{bar}` {pct}%"
    else:
        prog = "`──────────` 0%"
    rel = f"<t:{available_at}:R>"
    abs_t = f"<t:{available_at}:T>"
    suffix = f"(reste **{remaining}** fois aujourd’hui)" if remaining and remaining > 0 else ""
    return f"⏳ Calme-toi. Prochaine tentative {rel} • {abs_t} {suffix}\n{prog}"

def _daily_cap_message(action: str) -> str:
    reset_at = _next_reset_epoch("Europe/Paris", 8)
    base = DAILY_LIMIT_MSGS.get(action, "⛔ Tu as atteint ta limite quotidienne.")
    return base.format(reset_rel=f"<t:{reset_at}:R>", reset_time=f"<t:{reset_at}:T>")

def _check_limit(storage, user_id: int, action: str, cd: int, cap: int) -> tuple[bool, str | None]:
    if not hasattr(storage, "check_and_touch_action"):
        return True, None
    ok, wait, remaining = storage.check_and_touch_action(user_id, action, cd, cap)
    if ok:
        return True, None
    if remaining == 0:
        return False, _daily_cap_message(action)
    return False, _cooldown_message(storage, user_id, action, wait, remaining, cd)

# ───────── UI helpers (embeds & mini-anim) ─────────
def _now_ts() -> int:
    return int(time.time())

def _cooldown_field(storage, user_id: int, action: str, cd: int, cap: int) -> tuple[str, str]:
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
    show_cooldown: bool = False,   # on n’affiche pas par défaut
    show_money: bool = True,       # ── NEW: permet de cacher “Gain/Capital”
) -> discord.Embed:
    e = discord.Embed(
        title=f"{icon}  {title}",
        description=flavor,
        color=color
    )

    if show_money:
        e.add_field(name="💸 Gain", value=f"**{_fmt_delta(delta_cents)}**", inline=True)
        e.add_field(name="💰 Capital", value=f"**{fmt_eur(total_cents)}**", inline=True)

    if show_cooldown:
        name, val = _cooldown_field(storage, user_id, action_key, cooldown_s, cap)
        e.add_field(name=name, value=val, inline=False)

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
    anim = discord.Embed(title=title, description=pre_lines[0], color=color)
    await inter.response.send_message(embed=anim)
    msg = await inter.original_response()
    for line in pre_lines[1:]:
        await asyncio.sleep(delay)
        anim.description = line
        await msg.edit(embed=anim)
    await asyncio.sleep(delay)
    await msg.edit(embed=final_embed)

# ───────── Actions “moteur” (centimes) ─────────
def mendier_action(storage, user_id: int) -> dict:
    # calcule le delta (gain) mais NE TOUCHE PAS à la DB
    base = random.randint(MENDIER_MIN_CENTS, MENDIER_MAX_CENTS)
    power = compute_power(storage, user_id)
    flat_min = int(power.get("mendier_flat_min", 0))
    flat_max = int(power.get("mendier_flat_max", 0))
    flat = random.randint(flat_min, max(flat_min, flat_max)) if flat_max > 0 else 0
    mult = float(power.get("mendier_mult", 1.0))
    amount = max(1, int(round((base + flat) * mult)))
    return {"delta": amount}

def fouiller_action(storage, user_id: int) -> dict:
    # calcule seulement le delta (gain / neutre / perte), sans toucher la DB
    power = compute_power(storage, user_id)
    mult = float(power.get("fouiller_mult", 1.0))
    r = random.random()

    if r < 0.6:
        gain = int(round(random.randint(FOUILLER_GOOD_MIN, FOUILLER_GOOD_MAX) * mult))
        delta = gain
    elif r < 0.9:
        delta = 0
    else:
        # !!! caper la perte sur le solde RÉEL (ledger), pas players.money
        have = int(storage.get_money(user_id))   # ← utilise balance()
        perte_cap = min(FOUILLER_BAD_LOSS, max(0, have))
        delta = -perte_cap

    return {"delta": int(delta)}


def poches_action(storage, user_id: int) -> discord.Embed:
    # pour le test, on lit la source de vérité directe
    money_cents = balance(user_id)
    led = _sum_ledger(str(user_id))
    players_money = storage.get_player(user_id)["money"]

    e = discord.Embed(
        description=f"En fouillant un peu, t’arrives à racler : **{fmt_eur(money_cents)}**",
        color=discord.Color.dark_gold()
    )
    e.set_footer(text=f"data_dir={settings.data_dir} • ledger={fmt_eur(led)} • players={fmt_eur(players_money)}")
    return e

# ───────── Flows publics pour réutilisation (Start, autres UIs) ─────────
async def play_mendier(inter: Interaction, *, storage=None) -> bool:
    storage = storage or inter.client.storage
    p = storage.get_player(inter.user.id)
    if not p or not p.get("has_started"):
        await inter.response.send_message("🛑 Lance **/start** d’abord.", ephemeral=True)
        return False
    ok, msg = _check_limit(storage, inter.user.id, "mendier", MENDIER_COOLDOWN_S, MENDIER_DAILY_CAP)
    if not ok:
        await inter.response.send_message(msg, ephemeral=True)
        return False
    res = mendier_action(storage, inter.user.id)
    amount = int(res["delta"])

    # idempotent: une seule application par interaction
    new_money = credit_once(inter.user.id, amount, key=f"mendier:{inter.id}", reason="mendier")

    # stat (une seule fois ici, après succès)
    if hasattr(storage, "increment_stat"):
        storage.increment_stat(inter.user.id, "mendier_count", 1)

    final_embed = _result_embed(
        title="Mendier",
        icon="🥖",
        flavor="« Merci chef… la rue te sourit un peu aujourd’hui. »",
        delta_cents=amount,
        total_cents=new_money,  # ← utilise le solde renvoyé
        color=discord.Color.blurple(),
        storage=storage,
        user_id=inter.user.id,
        action_key="mendier",
        cooldown_s=MENDIER_COOLDOWN_S,
        cap=MENDIER_DAILY_CAP,
        show_cooldown=False,
        show_money=True,
    )
    await _play_anim_then_finalize(
        inter,
        title="🥖 Mendier",
        pre_lines=["🤲 Tu te poses au feu rouge…", "👀 Un passant fouille sa poche…", "💸 Une pièce glisse dans ta main."],
        color=discord.Color.blurple(),
        final_embed=final_embed,
        delay=0.6
    )
    return True

async def play_fouiller(inter: Interaction, *, storage=None) -> bool:
    storage = storage or inter.client.storage
    p = storage.get_player(inter.user.id)
    if not p or not p.get("has_started"):
        await inter.response.send_message("🛑 Lance **/start** d’abord.", ephemeral=True)
        return False
    ok, msg = _check_limit(storage, inter.user.id, "fouiller", FOUILLER_COOLDOWN_S, FOUILLER_DAILY_CAP)
    if not ok:
        await inter.response.send_message(msg, ephemeral=True)
        return False

    res = fouiller_action(storage, inter.user.id)

    # ── NEW: loot de canettes
    drop = maybe_grant_canettes_after_fouiller(storage, inter.user.id)  # int

    delta = int(res["delta"])

    # applique l'argent de façon idempotente
    if delta > 0:
        new_money = credit_once(inter.user.id, delta, key=f"fouiller:{inter.id}:gain", reason="fouiller")
        flavor = "🧳 Entre canettes et cartons… un truc revendable !"
        result_color = discord.Color.green()
    elif delta == 0:
        new_money = storage.get_money(inter.user.id)  # inchangé
        flavor = "🗑️ Bruit, odeur, rats… et rien au fond."
        result_color = discord.Color.gold()
    else:
        new_money = debit_once(inter.user.id, -delta, key=f"fouiller:{inter.id}:loss", reason="fouiller.loss")
        flavor = "🙄 Mauvaise rencontre. Le trottoir t’a coûté des sous."
        result_color = discord.Color.red()

    # stat (une seule fois ici)
    if hasattr(storage, "increment_stat"):
        storage.increment_stat(inter.user.id, "fouiller_count", 1)

    # Si canettes uniquement (pas d’argent), on n’affiche pas “Gain/Capital”
    canettes_only = (drop > 0 and delta == 0)
    if canettes_only:
        flavor = f"♻️ Tas de canettes récupérées : **+{drop}** (à compresser)"

    final_embed = _result_embed(
        title="Fouiller",
        icon="🗑️",
        flavor=flavor,
        delta_cents=delta,
        total_cents=new_money,  # ← utilise le nouveau solde
        color=result_color,
        storage=storage,
        user_id=inter.user.id,
        action_key="fouiller",
        cooldown_s=FOUILLER_COOLDOWN_S,
        cap=FOUILLER_DAILY_CAP,
        show_cooldown=False,
        show_money=not canettes_only,
    )

    if drop > 0 and not canettes_only:
        final_embed.add_field(name="♻️ Bonus", value=f"+{drop} canettes (à compresser)", inline=False)

    # Couleur NEUTRE pendant l'animation (pas de spoil)
    anim_color = discord.Color.dark_grey()

    await _play_anim_then_finalize(
        inter,
        title="🗑️ Fouiller",
        pre_lines=["♻️ Tu soulèves le couvercle…", "🔦 Tu éclaires tout au fond…", "🫳 Tu tires quelque chose…"],
        color=anim_color,             # ← neutre pendant l’anim
        final_embed=final_embed,
        delay=0.6
    )
    return True

# ───────── Slash (réutilisent aussi les flows publics) ─────────
def _build_group() -> app_commands.Group:
    return app_commands.Group(
        name="hess",
        description="La débrouille: mendier, fouiller, survivre."
    )

def register(tree: app_commands.CommandTree, guild_obj: discord.Object | None, client: discord.Client | None = None):
    hess = _build_group()

    @hess.command(name="mendier", description="Gagne quelques centimes (boosté par ton inventaire)")
    async def cmd_mendier(inter: Interaction):
        await play_mendier(inter)

    @hess.command(name="fouiller", description="Fouille une poubelle (boost léger via inventaire)")
    async def cmd_fouiller(inter: Interaction):
        await play_fouiller(inter)

    @hess.command(name="classement", description="Top 10 des joueurs les plus chargés")
    async def classement(inter: Interaction):
        storage = inter.client.storage
        rows = storage.top_richest(limit=10) if hasattr(storage, "top_richest") else []
        if not rows:
            await inter.response.send_message(
                "Aucun joueur classé pour l’instant. Fais **/start** puis **/hess mendier**.",
                ephemeral=True
            ); return
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
        embed = poches_action(storage, inter.user.id)
        await inter.response.send_message(embed=embed, ephemeral=not (p and p.get("has_started")))

    if guild_obj:
        tree.add_command(hess, guild=guild_obj)
    else:
        tree.add_command(hess)

# Compat setup
def setup_economy(tree: app_commands.CommandTree, guild_obj: discord.Object | None):
    register(tree, guild_obj, None)

# Alias public si besoin ailleurs
check_limit = _check_limit
# Expose les helpers si tu veux les réutiliser (optionnel)
build_result_embed = _result_embed
play_anim_then_finalize = _play_anim_then_finalize