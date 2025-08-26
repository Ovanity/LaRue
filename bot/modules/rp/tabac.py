# bot/modules/rp/tabac.py
from __future__ import annotations
import asyncio
import time
from typing import Optional
import random

import discord
from discord import app_commands, Interaction

from bot.modules.common.money import fmt_eur, MONEY_EMOJI_NAME, MONEY_EMOJI_ID
from bot.domain import economy as d_economy
from bot.domain import players as d_players
from bot.domain import stats as d_stats
from bot.domain import quotas as d_quotas

def _price_plain(cents: int) -> str:
    return fmt_eur(cents).split(" ", 1)[0]

# ───────────────────────────────────────────────────────────────────
# Tickets (prix/gains en CENTIMES) — payout moyen ≈ 63–68%
# ───────────────────────────────────────────────────────────────────
TICKETS: dict[str, dict] = {
    "banco": {
        "name": "BANCO",
        "price": 100,
        "pool": [(0, 430), (20, 120), (50, 150), (100, 190), (200, 80), (500, 25), (1000, 5)],
        "emoji": "🎟️",
        "desc": "Le classique. Souvent BAN, parfois CO. La FDP te dit merci.",
    },
    "astro": {
        "name": "ASTRO",
        "price": 200,
        "pool": [(0, 520), (50, 100), (100, 120), (200, 120), (300, 70), (500, 45), (1000, 15), (2000, 8), (5000, 2)],
        "emoji": "🪐",
        "desc": "Lis dans les étoiles… et retrouve surtout ton porte-monnaie vide.",
    },
    "goal": {
        "name": "GOAL!",
        "price": 300,
        "pool": [(0, 394), (100, 120), (150, 110), (200, 100), (300, 160), (500, 70), (1000, 30), (2000, 12), (5000, 4)],
        "emoji": "⚽️",
        "desc": "Tu tires… à côté 9 fois sur 10. Beau geste technique quand même.",
    },
    "cash": {
        "name": "CASH",
        "price": 500,
        "pool": [(0, 600), (200, 90), (300, 95), (500, 90), (1000, 70), (2000, 40), (5000, 10), (10000, 5)],
        "emoji": "💵",
        "desc": "Le nom fait rêver, la réalité fait rire (surtout la FDP).",
    },
    "million": {
        "name": "MILLIONNAIRE",
        "price": 1000,
        "pool": [(0, 720), (500, 120), (1000, 80), (2000, 40), (5000, 20), (10000, 12), (20000, 6), (50000, 2)],
        "emoji": "💰",
        "desc": "Tu ne deviendras pas millionnaire, mais eux oui si tu continues.",
    },
}

TABAC_COOLDOWN_S = 5
DEFAULT_TICKET_KEY = next(iter(TICKETS))

# ── Helpers ────────────────────────────────────────────────────────
def _touch_cooldown(user_id: int) -> tuple[bool, Optional[str]]:
    ok, wait, _ = d_quotas.check_and_touch(user_id, "tabac", TABAC_COOLDOWN_S, 999_999)
    if ok:
        return True, None
    available_at = int(time.time()) + int(wait)
    return False, f"⏳ Doucement… reviens <t:{available_at}:R>."

def _weight_pick_deterministic(pool: list[tuple[int, float]], rng: random.Random) -> int:
    total = float(sum(w for _, w in pool))
    x = rng.uniform(0.0, total)
    acc = 0.0
    for val, w in pool:
        acc += float(w)
        if x <= acc:
            return int(val)
    return int(pool[-1][0])

# ── Vue ────────────────────────────────────────────────────────────
class TabacView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=120)
        self.owner_id = owner_id
        self.message: Optional[discord.Message] = None
        self.current_key: Optional[str] = next(iter(TICKETS)) if TICKETS else None
        self._locked: bool = False

    async def _guard(self, inter: Interaction) -> bool:
        if inter.user.id != self.owner_id:
            await inter.response.send_message("🛑 C’est pas ton ticket, reuf.", ephemeral=True)
            return False
        return True

    def _base_embed(self) -> discord.Embed:
        if not TICKETS:
            return discord.Embed(
                title="🏪 Tabac du quartier",
                description="Aucun ticket disponible pour le moment.",
                color=discord.Color.dark_grey(),
            )
        if self.current_key not in TICKETS:
            self.current_key = next(iter(TICKETS))

        t = TICKETS[self.current_key]
        solde = fmt_eur(d_economy.balance(self.owner_id))

        e = discord.Embed(
            title=f"{t['emoji']}  {t['name']}",
            description=f"_{t['desc']}_",
            color=discord.Color.green(),
        )
        e.add_field(name="🎫 Prix", value=fmt_eur(t["price"]), inline=True)
        e.add_field(name="💰 Solde", value=solde, inline=True)
        e.add_field(name="\u200b", value="\u200b", inline=True)
        e.set_footer(text="Appuie sur 🎫 Gratter — rejoue tant que t’as des BiffCoins.")
        return e

    async def refresh_embed(self) -> None:
        if self.message:
            await self.message.edit(embed=self._base_embed(), view=self)

    def _set_gratter_disabled(self, disabled: bool) -> None:
        for child in self.children:
            if isinstance(child, discord.ui.Button) and child.custom_id == "tabac_gratter":
                child.disabled = disabled

    @discord.ui.select(
        placeholder="Choisis ton ticket…",
        options=[
            discord.SelectOption(
                label=f"{TICKETS[k]['name']}",
                value=k,
                description=f"Prix : {_price_plain(TICKETS[k]['price'])}",
                emoji=discord.PartialEmoji(name=MONEY_EMOJI_NAME, id=MONEY_EMOJI_ID),
            )
            for k in TICKETS
        ],
        custom_id="tabac_select",
    )
    async def select_ticket(self, inter: Interaction, select: discord.ui.Select):
        if not await self._guard(inter):
            return
        self.current_key = select.values[0]
        await inter.response.edit_message(embed=self._base_embed(), view=self)

    @discord.ui.button(label="🎫 Gratter", style=discord.ButtonStyle.success, custom_id="tabac_gratter")
    async def btn_gratter(self, inter: Interaction, _: discord.ui.Button):
        if not await self._guard(inter):
            return

        ok_cd, msg_cd = _touch_cooldown(inter.user.id)
        if not ok_cd:
            await inter.response.send_message(msg_cd or "⏳ Attends un peu.", ephemeral=True)
            return

        if self._locked:
            await inter.response.send_message("⏳ Déjà en train de gratter…", ephemeral=True)
            return
        self._locked = True
        self._set_gratter_disabled(True)

        t = TICKETS[self.current_key]
        price = int(t["price"])
        before = d_economy.balance(inter.user.id)
        if before < price:
            self._locked = False
            self._set_gratter_disabled(False)
            await inter.response.send_message(
                f"Il te manque **{fmt_eur(price - before)}** pour ce ticket.",
                ephemeral=True
            )
            return

        # On va faire plusieurs edits ⇒ defer puis edit le même message
        await inter.response.defer()

        # ── Débit idempotent (ledger)
        bet_key = f"tabac:{inter.id}:{self.current_key}:bet"
        d_economy.debit_once(inter.user.id, price, reason=f"tabac.bet:{self.current_key}", idem_key=bet_key)

        # RNG local déterministe (même résultat si Discord rejoue l’interaction)
        rng = random.Random(f"{inter.id}:{self.current_key}")
        symbols_pool = ["🍀", "⭐", "💎", "7️⃣", "🧧"]
        cover = "▩"

        def _latin_grid(rng: random.Random, sym_pool: list[str]) -> list[list[str]]:
            # Grille perdante : aucune ligne/colonne n'a 3 mêmes symboles.
            pool = sym_pool[:]
            rng.shuffle(pool)
            a, b, c = (pool + pool)[0:3]
            base = [[a, b, c], [b, c, a], [c, a, b]]
            rng.shuffle(base)
            cols = list(zip(*base))
            rng.shuffle(cols)
            return [list(r) for r in zip(*cols)]

        def _two_rows_no_triple(rng: random.Random, sym_pool: list[str], ban: str) -> list[list[str]]:
            others = [s for s in sym_pool if s != ban] or [ban]
            if len(others) == 1:
                o = others[0]
                rows = [[o, ban, o], [ban, o, ban]]
            else:
                pool = others[:]
                rng.shuffle(pool)
                a, b = pool[0], pool[1]
                rows = [[a, b, a], [b, a, b]]
            rng.shuffle(rows)
            return rows

        # Gain tiré de façon déterministe
        gain_cents = _weight_pick_deterministic(t["pool"], rng)

        # 1) Construire la grille finale en cohérence avec le résultat
        near_miss = False
        if gain_cents > 0:
            win_sym = rng.choice(symbols_pool)
            win_row = [win_sym, win_sym, win_sym]
            other_rows = _two_rows_no_triple(rng, symbols_pool, win_sym)
            rows = [None, None, None]  # type: ignore[list-item]
            win_idx = rng.randrange(3)
            rows[win_idx] = win_row
            idxs = [i for i in range(3) if i != win_idx]
            rows[idxs[0]] = other_rows[0]
            rows[idxs[1]] = other_rows[1]
        else:
            rows = _latin_grid(rng, symbols_pool)
            nm_sym = rng.choice(symbols_pool)
            miss_row = [nm_sym, nm_sym, rng.choice([s for s in symbols_pool if s != nm_sym])]
            rng.shuffle(miss_row)
            rows[rng.randrange(3)] = miss_row
            near_miss = True

        def _render_grid(final_rows: list[list[str]], revealed_cols: int, spinning_col: int | None) -> str:
            lines: list[str] = []
            for r in range(3):
                line: list[str] = []
                for c in range(3):
                    if c < revealed_cols:
                        line.append(final_rows[r][c])
                    elif spinning_col is not None and c == spinning_col:
                        line.append(random.choice(symbols_pool))  # spin visuel
                    else:
                        line.append(cover)
                lines.append(" ".join(line))
            return "```\n" + "\n".join(lines) + "\n```"

        # 2) Animation des colonnes
        e = self._base_embed()
        e.add_field(name="🎰 Grattage.", value=_render_grid(rows, 0, 0), inline=False)
        if self.message:
            await self.message.edit(embed=e, view=self)

        for col in range(3):
            for _ in range(5):
                await asyncio.sleep(0.12)
                e = self._base_embed()
                e.add_field(name="🎰 Grattage..", value=_render_grid(rows, col, col), inline=False)
                if self.message:
                    await self.message.edit(embed=e, view=self)
            e = self._base_embed()
            e.add_field(name="🎰 Grattage...", value=_render_grid(rows, col + 1, None), inline=False)
            if self.message:
                await self.message.edit(embed=e, view=self)

        # 3) Stat + crédit éventuel (idempotent)
        d_stats.incr(inter.user.id, "tabac_count", 1)

        if gain_cents > 0:
            win_key = f"tabac:{inter.id}:{self.current_key}:win"
            d_economy.credit_once(inter.user.id, gain_cents, reason=f"tabac.win:{self.current_key}", idem_key=win_key)

        # 4) Résultat final
        e = self._base_embed()
        e.add_field(
            name="🎰 Résultats",
            value="```\n" + "\n".join(" ".join(row) for row in rows) + "\n```",
            inline=False
        )

        if gain_cents > 0:
            e.color = discord.Color.gold()
            e.add_field(name="✨ Gagné", value=f"Tu prends **+{fmt_eur(gain_cents)}**. Pas mal, chef.", inline=False)
        else:
            e.color = discord.Color.dark_grey()
            tease = "C’était pas loin…" if near_miss else "Rien cette fois."
            e.add_field(name="😶", value=tease + " Essaye encore pour faire mieux.", inline=False)

        self._locked = False
        self._set_gratter_disabled(False)
        if self.message:
            await self.message.edit(embed=e, view=self)

    async def on_timeout(self) -> None:
        for child in self.children:
            if hasattr(child, "disabled"):
                child.disabled = True
        if self.message:
            try:
                e = discord.Embed(description="⏳ Le Tabac a fermé.", color=discord.Color.dark_grey())
                await self.message.edit(embed=e, view=None)
            except discord.NotFound:
                pass

# ── Commande ───────────────────────────────────────────────────────
def register(tree: app_commands.CommandTree, guild_obj: Optional[discord.Object], client: discord.Client | None = None):
    @tree.command(name="tabac", description="Kiosque à tickets à gratter")
    @app_commands.guilds(guild_obj) if guild_obj else (lambda f: f)
    async def tabac(inter: Interaction):
        if not d_players.get(inter.user.id).get("has_started"):
            await inter.response.send_message("🚀 Utilise **/start** avant.", ephemeral=True)
            return

        view = TabacView(inter.user.id)
        embed = view._base_embed()
        await inter.response.send_message(embed=embed, view=view)
        view.message = await inter.original_response()
