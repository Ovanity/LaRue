# bot/modules/rp/tabac.py
from __future__ import annotations
import random, asyncio, time
from datetime import datetime, UTC, timedelta
from typing import Optional

import discord
from discord import app_commands, Interaction
from zoneinfo import ZoneInfo

from bot.modules.common.money import fmt_eur
from bot.modules.rp.boosts import compute_power
from bot.modules.rp.economy import check_limit  # alias public de _check_limit

# ───────────────────────────
# Réglages Tabac (centimes)
# ───────────────────────────
TABAC_COOLDOWN_S = 45         # 45s entre tickets
TABAC_DAILY_CAP  = 10         # 20 tickets / jour / joueur

# Tickets: prix + distribution pondérée (poids sur 100000) ~RTP 65–75%
TICKETS: dict[str, dict] = {
    "ruelle": {   # 0,50 €
        "name": "Gratt'Ruelle",
        "price": 50,
        "weights": {
            0:       64000,
            50:      24000,
            100:      8500,
            200:      2800,
            500:       600,
            1000:      90,
            5000:      10,
        },
    },
    "banco": {    # 1,00 €
        "name": "Banco du coin",
        "price": 100,
        "weights": {
            0:       65000,
            100:     23000,
            200:      9000,
            500:      2500,
            1000:      430,
            5000:       60,
            10000:      10,
        },
    },
    "cash": {     # 2,00 €
        "name": "CASH Biff",
        "price": 200,
        "weights": {
            0:       62000,
            200:     25000,
            400:      9000,
            1000:     2800,
            2000:      900,
            5000:      250,
            10000:      40,
            20000:      10,
        },
    },
    "jackpot": {  # 5,00 €
        "name": "Jackpot Tabac",
        "price": 500,
        "weights": {
            0:       65000,
            500:     23200,
            1000:     8000,
            2000:     2400,
            5000:      900,
            10000:     350,
            20000:      100,
            50000:       40,
            100000:      10,
        },
    },
}

# ───────────────────────────
# Helpers
# ───────────────────────────
def _rtp(weights: dict[int,int], price: int) -> float:
    exp = sum(int(p)*int(w) for p,w in weights.items())/100000.0
    return (exp/max(1,price))*100.0

def _next_reset_epoch(tz="Europe/Paris", hour=8) -> int:
    now = datetime.now(ZoneInfo(tz))
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    return int(target.astimezone(UTC).timestamp())

def _draw_prize(weights: dict[int,int], power: dict) -> int:
    w = dict(weights)
    bias_small = int(float(power.get("tabac_bias_small", 0)))
    if bias_small and 0 in w and w[0] > bias_small:
        small_keys = [k for k in w if 0 < k <= 1000]
        if small_keys:
            take = min(bias_small, w[0]-1)
            w[0] -= take
            add_each = max(1, take//len(small_keys))
            for k in small_keys: w[k] += add_each

    roll = random.randint(1, 100000)
    acc, picked = 0, 0
    for prize, wt in sorted(w.items(), key=lambda kv: kv[1], reverse=True):
        acc += int(wt)
        if roll <= acc:
            picked = int(prize)
            break

    mult = float(power.get("tabac_mult", 1.0))
    return int(round(picked*mult)) if picked>0 else 0

def _progress(pct: int, width=10) -> str:
    filled = max(0, min(width, (pct*width)//100))
    return "█"*filled + "─"*(width-filled)

# ───────────────────────────
# Vue interactive
# ───────────────────────────
class TabacView(discord.ui.View):
    def __init__(self, owner_id: int, storage, *, timeout: Optional[float]=180):
        super().__init__(timeout=timeout)
        self.owner_id = owner_id
        self.storage = storage
        self.message: Optional[discord.Message] = None
        self.current_key: str = "ruelle"

    async def _guard(self, inter: Interaction) -> bool:
        if inter.user.id != self.owner_id:
            await inter.response.send_message("🛑 Pas ton kiosque, reuf.", ephemeral=True)
            return False
        return True

    def _base_embed(self) -> discord.Embed:
        t = TICKETS[self.current_key]
        price = int(t["price"])
        rtp   = _rtp(t["weights"], price)
        bal   = self.storage.get_money(self.owner_id)
        state = self.storage.get_action_state(self.owner_id, "tabac") if hasattr(self.storage,"get_action_state") else {"count":0}
        remaining = max(0, TABAC_DAILY_CAP - int(state.get("count", 0)))
        reset_at = _next_reset_epoch()
        e = discord.Embed(
            title="🚬 Tabac — Comptoir à gratter",
            color=discord.Color.green(),
            description=(
                f"**Ticket :** {t['name']}\n"
                f"**Prix :** {fmt_eur(price)} • **RTP théorique :** `{rtp:.1f}%`\n"
                f"**Solde :** {fmt_eur(bal)}\n"
                f"**Aujourd’hui :** {remaining} restant(s) • Reset {f'<t:{reset_at}:R>'}\n"
            ),
        )
        e.set_footer(text=f"Emitted @ {datetime.now(UTC).strftime('%H:%M:%S UTC')} • LaRue.exe")
        return e

    async def _refresh(self):
        if self.message:
            await self.message.edit(embed=self._base_embed(), view=self)

    @discord.ui.select(
        placeholder="Choisis ton ticket…",
        min_values=1, max_values=1,
        options=[
            discord.SelectOption(label=TICKETS[k]["name"], value=k, description=f"Prix {fmt_eur(TICKETS[k]['price'])}")
            for k in ("ruelle","banco","cash","jackpot")
        ],
        custom_id="tabac_select"
    )
    async def select_ticket(self, inter: Interaction, select: discord.ui.Select):
        if not await self._guard(inter): return
        self.current_key = select.values[0]
        await inter.response.defer()
        await self._refresh()

    @discord.ui.button(label="🎫 Acheter & gratter", style=discord.ButtonStyle.primary, custom_id="tabac_buy")
    async def buy_and_scratch(self, inter: Interaction, _: discord.ui.Button):
        if not await self._guard(inter): return
        await inter.response.defer()
        key = self.current_key
        t = TICKETS.get(key)
        if not t:
            await inter.followup.send("❌ Ticket introuvable.", ephemeral=True); return

        ok, msg = check_limit(self.storage, self.owner_id, "tabac", TABAC_COOLDOWN_S, TABAC_DAILY_CAP)
        if not ok:
            await inter.followup.send(msg, ephemeral=True); return

        price = int(t["price"])
        if not self.storage.try_spend(self.owner_id, price):
            bal = self.storage.get_money(self.owner_id)
            await inter.followup.send(f"💸 Pas assez. Prix: {fmt_eur(price)} • Solde: {fmt_eur(bal)}", ephemeral=True)
            return

        if not self.message:
            self.message = await inter.original_response()

        # frame 1 — préparation
        bal0 = self.storage.get_money(self.owner_id)
        embed = discord.Embed(
            title=f"🎫 {t['name']}",
            description=(
                "```\n"
                "┌───────────────┐\n"
                "│  ▒ ▒ ▒  ▒ ▒ ▒ │   grattage en cours…\n"
                "│  ▒ ▒ ▒  ▒ ▒ ▒ │\n"
                "│  ▒ ▒ ▒  ▒ ▒ ▒ │\n"
                "└───────────────┘\n"
                "```"
            ),
            color=discord.Color.orange()
        )
        embed.add_field(name="Ticket", value=fmt_eur(price))
        embed.add_field(name="Solde",  value=fmt_eur(bal0))
        await self.message.edit(embed=embed, view=self)
        await asyncio.sleep(0.9)

        # tirage
        power = compute_power(self.storage, self.owner_id) if callable(compute_power) else {}
        win = _draw_prize(t["weights"], power)

        # frame 2 — reveal partiel
        for pct in (35, 70, 100):
            bar = _progress(pct)
            embed.description = (
                "```\n"
                "┌───────────────┐\n"
                f"│  {bar[:3]} {bar[3:6]} {bar[6:]} │   grattage {pct}%\n"
                "│  ▒ ▒ ▒  ▒ ▒ ▒ │\n"
                "│  ▒ ▒ ▒  ▒ ▒ ▒ │\n"
                "└───────────────┘\n"
                "```"
            )
            await self.message.edit(embed=embed, view=self)
            await asyncio.sleep(0.35)

        # résultat & solde final
        if win > 0:
            self.storage.add_money(self.owner_id, win)
            net = win - price
            color = discord.Color.gold()
            result = f"**Gagné : {fmt_eur(win)}**  •  Net: {fmt_eur(net)} 🎉"
        else:
            net = -price
            color = discord.Color.dark_grey()
            result = f"Perdu… (− {fmt_eur(price)})"

        bal1 = self.storage.get_money(self.owner_id)
        embed = discord.Embed(
            title=f"🎫 {t['name']}",
            description=result,
            color=color
        )
        embed.set_footer(text=f"Solde: {fmt_eur(bal1)} • {datetime.now(UTC).strftime('%H:%M:%S UTC')}")
        await self.message.edit(embed=embed, view=self)

        if hasattr(self.storage, "increment_stat"):
            self.storage.increment_stat(self.owner_id, "tabac_count", 1)

    async def on_timeout(self):
        for c in self.children:
            if hasattr(c, "disabled"): c.disabled = True
        if self.message:
            try:
                e = self._base_embed()
                e.color = discord.Color.dark_grey()
                e.description = (e.description or "") + "\n\n`Kiosque endormi… rouvre la commande pour continuer.`"
                await self.message.edit(embed=e, view=None)
            except discord.NotFound:
                pass

# ───────────────────────────
# Slash commands
# ───────────────────────────
tabac = app_commands.Group(name="tabac", description="Le tabac du coin — tickets à gratter.")

@tabac.command(name="kiosque", description="Ouvre le comptoir à gratter (tickets + animations)")
async def tabac_kiosque(inter: Interaction):
    storage = inter.client.storage
    p = storage.get_player(inter.user.id)
    if not p or not p.get("has_started"):
        await inter.response.send_message("🚀 Utilise **/start** avant.", ephemeral=True)
        return

    view = TabacView(inter.user.id, storage)
    embed = view._base_embed()
    await inter.response.send_message(embed=embed, view=view)
    view.message = await inter.original_response()

@tabac.command(name="liste", description="Liste des tickets disponibles (prix & RTP)")
async def tabac_liste(inter: Interaction):
    lines = []
    for key, t in TICKETS.items():
        price = int(t["price"]); rtp = _rtp(t["weights"], price)
        lines.append(f"**{t['name']}** — Prix: {fmt_eur(price)} • RTP théorique: `{rtp:.1f}%`  → `/tabac kiosque`")
    embed = discord.Embed(
        title="🚬 Tabac — Tickets",
        description="\n\n".join(lines),
        color=discord.Color.blurple()
    )
    await inter.response.send_message(embed=embed, ephemeral=True)

def register(tree: app_commands.CommandTree, guild_obj: Optional[discord.Object], client: Optional[discord.Client]=None):
    if guild_obj: tree.add_command(tabac, guild=guild_obj)
    else:         tree.add_command(tabac)