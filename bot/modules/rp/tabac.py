# bot/modules/rp/tabac.py
from __future__ import annotations
import asyncio
import random
import time
from typing import Optional

import discord
from discord import app_commands, Interaction

from bot.modules.common.money import fmt_eur, MONEY_EMOJI_NAME, MONEY_EMOJI_ID

# PartialEmoji for select options (shows the real emoji, not the <:...> text)
MONEY_PARTIAL = discord.PartialEmoji(name=MONEY_EMOJI_NAME, id=MONEY_EMOJI_ID)

def _price_plain(cents: int) -> str:
    # fmt_eur returns "12,34 <:BiffCoins:...>", we want only "12,34" for the select description
    return fmt_eur(cents).split(" ", 1)[0]

# ───────────────────────────────────────────────────────────────────
# Tickets (prix/gains en CENTIMES)
# ───────────────────────────────────────────────────────────────────
# Tickets (prix/gains en CENTIMES) — payout moyen ≈ 63–68%
TICKETS: dict[str, dict] = {
    "banco": {
        "name": "BANCO",
        "price": 100,  # 1,00 €
        "pool": [      # (gain_cents, poids)
            (0, 430), (20, 120), (50, 150), (100, 190),
            (200, 80), (500, 25), (1000, 5),
        ],  # EV ≈ 0,62 € → 62%
        "emoji": "🎟️",
        "desc": "Le classique à 1 €. Souvent BAN, parfois CO. La FDJ te dit merci.",
    },
    "astro": {
        "name": "ASTRO",
        "price": 200,  # 2,00 €
        "pool": [
            (0, 520), (50, 100), (100, 120), (200, 120),
            (300, 70), (500, 45), (1000, 15), (2000, 8), (5000, 2),
        ],  # EV ≈ 1,26 € → 63%
        "emoji": "🪐",
        "desc": "Lis dans les étoiles… et retrouve surtout ton porte-monnaie vide.",
    },
    "goal": {
        "name": "GOAL!",
        "price": 300,  # 3,00 €
        "pool": [
            (0, 394), (100, 120), (150, 110), (200, 100),
            (300, 160), (500, 70), (1000, 30), (2000, 12), (5000, 4),
        ],  # EV ≈ 2,06 € → 69%
        "emoji": "⚽️",
        "desc": "Tu tires… à côté 9 fois sur 10. Beau geste technique quand même.",
    },
    "cash": {
        "name": "CASH",
        "price": 500,  # 5,00 €
        "pool": [
            (0, 600), (200, 90), (300, 95), (500, 90),
            (1000, 70), (2000, 40), (5000, 10), (10000, 5),
        ],  # EV ≈ 3,42 € → 68%
        "emoji": "💵",
        "desc": "Le nom fait rêver, la réalité fait rire (surtout la FDJ).",
    },
    "million": {
        "name": "MILLIONNAIRE",
        "price": 1000,  # 10,00 €
        "pool": [
            (0, 720), (500, 120), (1000, 80), (2000, 40),
            (5000, 20), (10000, 12), (20000, 6), (50000, 2),
        ],  # EV ≈ 6,60 € → 66%
        "emoji": "💰",
        "desc": "Tu ne deviendras pas millionnaire, mais eux oui si tu continues.",
    },
}

TABAC_COOLDOWN_S = 5  # anti-spam léger
DEFAULT_TICKET_KEY = next(iter(TICKETS))

# ── Helpers storage-safe ───────────────────────────────────────────
def _get_money(storage, user_id: int) -> int:
    if hasattr(storage, "get_money"):
        return int(storage.get_money(user_id))
    return int(storage.get_player(user_id)["money"])

def _try_spend(storage, user_id: int, amount: int) -> bool:
    amt = int(amount)
    if amt <= 0:
        return True
    if hasattr(storage, "try_spend"):
        return bool(storage.try_spend(user_id, amt))
    p = storage.get_player(user_id)
    if p["money"] < amt:
        return False
    storage.update_player(user_id, money=p["money"] - amt)
    return True

def _add_money(storage, user_id: int, amount: int) -> int:
    amt = int(amount)
    if hasattr(storage, "add_money"):
        return storage.add_money(user_id, amt)["money"]
    p = storage.get_player(user_id)
    return storage.update_player(user_id, money=p["money"] + amt)["money"]

def _touch_cooldown(storage, user_id: int) -> tuple[bool, Optional[str]]:
    if hasattr(storage, "check_and_touch_action"):
        ok, wait, _remaining = storage.check_and_touch_action(user_id, "tabac", TABAC_COOLDOWN_S, 999999)
        if not ok:
            available_at = int(time.time()) + int(wait)
            return False, f"⏳ Doucement… reviens <t:{available_at}:R>."
    return True, None

def _weight_pick(pool: list[tuple[int, float]]) -> int:
    gains, weights = zip(*pool)
    return int(random.choices(gains, weights=weights, k=1)[0])

# ── Vue ────────────────────────────────────────────────────────────
class TabacView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=120)
        self.owner_id = owner_id
        self.message: Optional[discord.Message] = None
        # clé par défaut = première entrée disponible dans TICKETS
        self.current_key: Optional[str] = next(iter(TICKETS)) if TICKETS else None
        self._locked: bool = False

    async def _guard(self, inter: Interaction) -> bool:
        if inter.user.id != self.owner_id:
            await inter.response.send_message("🛑 C’est pas ton ticket, reuf.", ephemeral=True)
            return False
        return True

    def _base_embed(self, storage) -> discord.Embed:
        if not TICKETS:
            return discord.Embed(
                title="🏪 Tabac du quartier",
                description="Aucun ticket disponible pour le moment.",
                color=discord.Color.dark_grey()
            )

        if self.current_key not in TICKETS:
            self.current_key = next(iter(TICKETS))

        t = TICKETS[self.current_key]
        solde = fmt_eur(_get_money(storage, self.owner_id))

        e = discord.Embed(
            title=f"{t['emoji']}  {t['name']}",
            description=f"_{t['desc']}_",
            color=discord.Color.green()
        )
        # Ligne infos (alignées)
        e.add_field(name="🎫 Prix", value=fmt_eur(t["price"]), inline=True)
        e.add_field(name="💰 Solde", value=solde, inline=True)
        # Filler pour compléter la ligne et éviter l’espace vertical
        e.add_field(name="\u200b", value="\u200b", inline=True)

        e.set_footer(text="Appuie sur 🎫 Gratter — rejoue tant que t’as des BiffCoins.")
        return e

    async def refresh_embed(self, storage) -> None:
        if self.message:
            await self.message.edit(embed=self._base_embed(storage), view=self)

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
                description=f"Prix : {fmt_eur(TICKETS[k]['price']).split(' ', 1)[0]}",
                emoji=discord.PartialEmoji(name=MONEY_EMOJI_NAME, id=MONEY_EMOJI_ID),
            )
            for k in TICKETS
        ],
        custom_id="tabac_select"
    )
    async def select_ticket(self, inter: Interaction, select: discord.ui.Select):
        if not await self._guard(inter):
            return
        self.current_key = select.values[0]
        await inter.response.edit_message(embed=self._base_embed(inter.client.storage), view=self)

    @discord.ui.button(label="🎫 Gratter", style=discord.ButtonStyle.success, custom_id="tabac_gratter")
    async def btn_gratter(self, inter: Interaction, _: discord.ui.Button):
        if not await self._guard(inter): return
        storage = inter.client.storage

        ok_cd, msg_cd = _touch_cooldown(storage, inter.user.id)
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
        have = _get_money(storage, inter.user.id)
        if have < price:
            self._locked = False
            self._set_gratter_disabled(False)
            await inter.response.send_message(
                f"Il te manque **{fmt_eur(price - have)}** pour ce ticket.",
                ephemeral=True
            )
            return

        # On va faire plusieurs edits ⇒ defer l’interaction, puis edit le même message
        await inter.response.defer()

        # Débit
        if not _try_spend(storage, inter.user.id, price):
            self._locked = False
            self._set_gratter_disabled(False)
            await inter.followup.send("💳 Paiement refusé, reviens avec des biftons.", ephemeral=True)
            return

        # Préparation carte (cohérente avec le résultat)
        # ── Scratch with slot-style spins, near-misses, and light copy ────────────────
        cover = "▩"
        symbols_pool = ["🍀", "⭐", "💎", "7️⃣", "🧧"]
        gain_cents = _weight_pick(t["pool"])

        def _latin_grid(sym_pool: list[str]) -> list[list[str]]:
            # Grille perdante : aucune ligne/colonne n'a 3 mêmes symboles.
            a, b, c = (sym_pool + sym_pool)[0:3] if len(sym_pool) < 3 else random.sample(sym_pool, 3)
            base = [[a, b, c], [b, c, a], [c, a, b]]
            random.shuffle(base)
            cols = list(zip(*base))
            random.shuffle(cols)
            return [list(r) for r in zip(*cols)]

        def _two_rows_no_triple(sym_pool: list[str], ban: str) -> list[list[str]]:
            # Deux lignes sans triplé, et sans colonnes 3×ban.
            others = [s for s in sym_pool if s != ban] or [ban]
            if len(others) == 1:
                o = others[0]
                rows = [[o, ban, o], [ban, o, ban]]
            else:
                a, b = random.sample(others, 2)
                rows = [[a, b, a], [b, a, b]]
            random.shuffle(rows)
            return rows

        # 1) Construire la grille finale en cohérence avec le résultat
        near_miss = False
        if gain_cents > 0:
            win_sym = random.choice(symbols_pool)
            win_row = [win_sym, win_sym, win_sym]
            other_rows = _two_rows_no_triple(symbols_pool, win_sym)
            rows = [None, None, None]  # type: ignore[list-item]
            win_idx = random.randrange(3)
            rows[win_idx] = win_row
            idxs = [i for i in range(3) if i != win_idx]
            rows[idxs[0]] = other_rows[0]
            rows[idxs[1]] = other_rows[1]
        else:
            # Grille perdante + une ligne “presque” (2/3 identiques)
            rows = _latin_grid(symbols_pool)
            nm_sym = random.choice(symbols_pool)
            miss_row = [nm_sym, nm_sym, random.choice([s for s in symbols_pool if s != nm_sym])]
            random.shuffle(miss_row)
            rows[random.randrange(3)] = miss_row
            near_miss = True

        # Helper rendu avec colonne en spin
        def _render_grid(final_rows: list[list[str]], revealed_cols: int, spinning_col: int | None) -> str:
            lines: list[str] = []
            for r in range(3):
                line: list[str] = []
                for c in range(3):
                    if c < revealed_cols:
                        line.append(final_rows[r][c])
                    elif spinning_col is not None and c == spinning_col:
                        line.append(random.choice(symbols_pool))
                    else:
                        line.append(cover)
                lines.append(" ".join(line))
            return "```\n" + "\n".join(lines) + "\n```"

        # 2) Afficher l’état couvert puis animer chaque colonne (3–5 frames rapides)
        e = self._base_embed(storage)
        e.add_field(name="🎰 Grattage.", value=_render_grid(rows, 0, 0), inline=False)
        if self.message:
            await self.message.edit(embed=e, view=self)

        for col in range(3):
            # “spin” court pour cette colonne
            for _ in range(5):
                await asyncio.sleep(0.12)
                e = self._base_embed(storage)
                e.add_field(name="🎰 Grattage..", value=_render_grid(rows, col, col), inline=False)
                if self.message:
                    await self.message.edit(embed=e, view=self)
            # verrouille la colonne révélée
            e = self._base_embed(storage)
            e.add_field(name="🎰 Grattage...", value=_render_grid(rows, col + 1, None), inline=False)
            if self.message:
                await self.message.edit(embed=e, view=self)

        # 3) Crédit + message de résultat (sans tableau “Mise/Gain/Net”)
        if hasattr(storage, "increment_stat"):
            storage.increment_stat(inter.user.id, "tabac_count", 1)

        final_money = _add_money(storage, inter.user.id, gain_cents)

        e = self._base_embed(storage)
        # Grille finale figée
        e.add_field(
            name="🎰 Résultats",
            value="```\n" + "\n".join(" ".join(row) for row in rows) + "\n```",
            inline=False
        )

        if gain_cents > 0:
            # Win = message court & euphorisant
            e.color = discord.Color.gold()
            e.add_field(
                name="✨ Gagné",
                value=f"Tu prends **+{fmt_eur(gain_cents)}**. Pas mal, chef.",
                inline=False
            )
        else:
            # Perte = soft landing + near-miss tease (sans chiffres)
            e.color = discord.Color.dark_grey()
            tease = "C’était pas loin…" if near_miss else "Rien cette fois."
            e.add_field(
                name="😶",
                value=tease + " Essaye encore pour faire mieux.",
                inline=False
            )

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
                e = discord.Embed(
                    description="⏳ Le Tabac a fermé.",
                    color=discord.Color.dark_grey()
                )
                await self.message.edit(embed=e, view=None)
            except discord.NotFound:
                pass

# ── Commande ───────────────────────────────────────────────────────
def register(tree: app_commands.CommandTree, guild_obj: Optional[discord.Object], client: discord.Client | None = None):
    @tree.command(name="tabac", description="Kiosque à tickets à gratter")
    @app_commands.guilds(guild_obj) if guild_obj else (lambda f: f)
    async def tabac(inter: Interaction):
        storage = inter.client.storage
        p = storage.get_player(inter.user.id)
        if not p or not p.get("has_started"):
            await inter.response.send_message("🚀 Utilise **/start** avant.", ephemeral=True)
            return

        view = TabacView(inter.user.id)
        embed = view._base_embed(storage)
        await inter.response.send_message(embed=embed, view=view)
        view.message = await inter.original_response()