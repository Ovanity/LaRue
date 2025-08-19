# bot/modules/rp/tabac.py
from __future__ import annotations
import asyncio
import random
import time
from typing import Optional

import discord
from discord import app_commands, Interaction

from bot.modules.common.money import fmt_eur

# ───────────────────────────────────────────────────────────────────
# Tickets (prix/gains en CENTIMES)
# ───────────────────────────────────────────────────────────────────
TICKETS: dict[str, dict] = {
    "micro": {
        "name": "Micro-Gratte",
        "price": 50,   # 0,50 €
        "pool": [      # (gain_cents, poids)
            (0, 320), (5, 90), (10, 80), (20, 120),
            (50, 220), (100, 120), (200, 20), (500, 5),
        ],  # EV ≈ 34c → 68%
        "emoji": "🟩",
        "desc": "Le gratte-vite pas cher. Souvent rien, parfois le ticket remboursé.",
    },
    "canette": {
        "name": "Gratte-Canette",
        "price": 100,  # 1,00 €
        "pool": [
            (0, 380), (10, 60), (20, 90), (50, 150),
            (100, 200), (200, 90), (500, 25), (1000, 5),
        ],  # EV ≈ 65c → 65%
        "emoji": "🟨",
        "desc": "Le classique du kiosque. Remboursé assez souvent, bonus occasionnels.",
    },
    "poche": {
        "name": "Jackpot de Poche",
        "price": 200,  # 2,00 €
        "pool": [
            (0, 560), (50, 60), (100, 90), (150, 80),
            (200, 110), (400, 60), (1000, 30), (2000, 8), (5000, 2),
        ],  # EV ≈ 1,26 € → 63%
        "emoji": "🟦",
        "desc": "Petit frisson à 2 €. Parfois plus qu’un remboursement.",
    },
    "pave": {
        "name": "Pavé Doré",
        "price": 300,  # 3,00 €
        "pool": [
            (0, 400), (100, 60), (150, 50), (200, 110),
            (300, 180), (500, 60), (1000, 30), (2000, 8), (5000, 2),
        ],  # EV ≈ 1,95 € → 65%
        "emoji": "🟥",
        "desc": "Un peu plus piquant. De vraies lignes gagnantes peuvent tomber.",
    },
    "trottoir": {
        "name": "Loto Trottoir",
        "price": 500,  # 5,00 €
        "pool": [
            (0, 800), (200, 140), (300, 130), (500, 130),
            (1000, 120), (2000, 60), (5000, 8), (10000, 2), (20000, 1),
        ],  # EV ≈ 3,25 € → 65%
        "emoji": "🟪",
        "desc": "Le gros ticket. Grosse variance, jackpot rarissime mais réel.",
    },
}

TABAC_COOLDOWN_S = 5  # anti-spam léger

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
        self.current_key: str = "micro"
        self._locked: bool = False

    async def _guard(self, inter: Interaction) -> bool:
        if inter.user.id != self.owner_id:
            await inter.response.send_message("🛑 C’est pas ton ticket, reuf.", ephemeral=True)
            return False
        return True

    def _base_embed(self, storage) -> discord.Embed:
        t = TICKETS[self.current_key]
        e = discord.Embed(
            title="🏪 Tabac du quartier",
            description=(
                f"Ticket **{t['name']}** {t['emoji']}\n"
                f"Prix: **{fmt_eur(t['price'])}**  •  Ton solde: **{fmt_eur(_get_money(storage, self.owner_id))}**\n"
                f"*{t['desc']}*"
            ),
            color=discord.Color.green()
        )
        e.set_footer(text="Appuie sur 🎫 Gratter. Rejoue tant que t’as de la monnaie.")
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
            discord.SelectOption(label=TICKETS[k]["name"], value=k, description=fmt_eur(TICKETS[k]["price"]))
            for k in TICKETS
        ],
        custom_id="tabac_select"
    )
    async def select_ticket(self, inter: Interaction, select: discord.ui.Select):
        if not await self._guard(inter): return
        self.current_key = select.values[0]
        # Édite le même message
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

        # Préparation carte
        cover = "▩"
        symbols_pool = ["🍀", "⭐", "💎", "7️⃣", "🧧"]
        gain_cents = _weight_pick(t["pool"])

        # grille solution
        if gain_cents > 0:
            sym = random.choice(symbols_pool)
            win_line = random.randrange(3)
            rows = [[random.choice(symbols_pool) for _ in range(3)] for __ in range(3)]
            rows[win_line] = [sym, sym, sym]
        else:
            rows = [[random.choice(symbols_pool) for _ in range(3)] for __ in range(3)]

        # 1) état couvert
        e = self._base_embed(storage)
        covered = "\n".join([" ".join([cover, cover, cover]) for _ in range(3)])
        e.add_field(name="Carte", value=f"```\n{covered}\n```", inline=False)
        if self.message:
            await self.message.edit(embed=e, view=self)

        # 2) révélation progressive colonne par colonne
        for step in range(3):
            await asyncio.sleep(0.8)
            reveal_lines = []
            for r in range(3):
                line = []
                for c in range(3):
                    line.append(rows[r][c] if c <= step else cover)
                reveal_lines.append(" ".join(line))
            e = self._base_embed(storage)
            e.add_field(name="Carte", value=f"```\n" + "\n".join(reveal_lines) + "\n```", inline=False)
            if self.message:
                await self.message.edit(embed=e, view=self)

        # 3) crédit + résultat
        if hasattr(storage, "increment_stat"):
            storage.increment_stat(inter.user.id, "tabac_count", 1)

        final_money = _add_money(storage, inter.user.id, gain_cents)

        res_text = (
            f"🎉 **Gagné {fmt_eur(gain_cents)} !**"
            if gain_cents > 0 else
            "😬 Rien du tout… la chance reviendra."
        )
        e = self._base_embed(storage)
        e.add_field(
            name="Carte",
            value="```\n" + "\n".join(" ".join(row) for row in rows) + "\n```",
            inline=False
        )
        e.add_field(
            name="Résultat",
            value=(
                f"{res_text}\n"
                f"**Solde**: {fmt_eur(final_money)}\n"
            ),
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
                    description="⏳ Le kiosque a fermé. Rouvre **/tabac** pour rejouer.",
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