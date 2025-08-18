# bot/modules/rp/tabac.py
from __future__ import annotations
import asyncio
import random
from typing import Optional

import discord
from discord import app_commands, Interaction

from bot.modules.common.money import fmt_eur

# ───────────────────────────────────────────────────────────────────
# Tickets (prix en centimes) — proba ~ inspirées FDJ mais adaptées à l'économie du jeu
# Chaque ticket a un pool de gains (en centimes) avec des poids.
# L'espérance reste < prix pour la santé de l'économie.
# ───────────────────────────────────────────────────────────────────
TICKETS: dict[str, dict] = {
    "micro": {
        "name": "Micro-Gratte",
        "price": 50,  # 0,50€
        "pool": [
            # (gain_cents, poids)
            (0, 65),
            (10, 10), (20, 8), (30, 6), (50, 4),      # petits lots (souvent < prix)
            (100, 3), (150, 2),                        # moyens
            (500, 2), (1000, 0.5),                     # 5€ | 10€
        ],
        "emoji": "🟩",
        "desc": "Gratte-vite pas cher. De temps en temps, un café payé.",
    },
    "poche": {
        "name": "Jackpot de Poche",
        "price": 200,  # 2,00€
        "pool": [
            (0, 70),
            (50, 8), (100, 7), (150, 5), (200, 4),
            (400, 3), (600, 1.8), (1000, 1.0),
            (2500, 0.6), (5000, 0.4),                  # 25€ | 50€
        ],
        "emoji": "🟦",
        "desc": "Format poche, peut tomber un petit billet.",
    },
    "trottoir": {
        "name": "Loto Trottoir",
        "price": 500,  # 5,00€
        "pool": [
            (0, 75),
            (100, 7), (200, 5), (300, 4), (500, 3),
            (1000, 2.5), (1500, 1.5), (3000, 1.0),
            (10000, 0.5), (20000, 0.3),                # 100€ | 200€
        ],
        "emoji": "🟪",
        "desc": "Le gros délire. Rarement la folie, parfois la paye.",
    },
}

TABAC_COOLDOWN_S = 5  # anti-spam léger pour /tabac


# ───────────────────────────────────────────────────────────────────
# Helpers storage-safe
# ───────────────────────────────────────────────────────────────────
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
    if hasattr(storage, "add_money"):
        return storage.add_money(user_id, int(amount))["money"]
    p = storage.get_player(user_id)
    return storage.update_player(user_id, money=p["money"] + int(amount))["money"]

def _touch_cooldown(storage, user_id: int) -> tuple[bool, Optional[str]]:
    if hasattr(storage, "check_and_touch_action"):
        ok, wait, remaining = storage.check_and_touch_action(user_id, "tabac", TABAC_COOLDOWN_S, 999999)
        if not ok:
            return False, f"⏳ Laisse chauffer la monnaie… reviens <t:{int(asyncio.get_running_loop().time()) + int(wait)}:R>."
    return True, None

def _weight_pick(pool: list[tuple[int, float]]) -> int:
    # random.choices pour poids flottants
    gains, weights = zip(*pool)
    return int(random.choices(gains, weights=weights, k=1)[0])


# ───────────────────────────────────────────────────────────────────
# Vue
# ───────────────────────────────────────────────────────────────────
class TabacView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=120)
        self.owner_id = owner_id
        self.message: Optional[discord.Message] = None
        self.current_key: str = "micro"
        self._locked: bool = False  # évite double-click

    async def _guard(self, inter: Interaction) -> bool:
        if inter.user.id != self.owner_id:
            await inter.response.send_message("🛑 C’est pas ton ticket, reuf.", ephemeral=True)
            return False
        return True

    def _base_embed(self, storage) -> discord.Embed:
        ticket = TICKETS[self.current_key]
        price = ticket["price"]
        money = _get_money(storage, self.owner_id)

        e = discord.Embed(
            title="🏪 Tabac du quartier",
            description=(
                f"Ticket **{ticket['name']}** {ticket['emoji']}\n"
                f"Prix: **{fmt_eur(price)}**  •  Ton solde: **{fmt_eur(money)}**\n"
                f"*{ticket['desc']}*"
            ),
            color=discord.Color.green()
        )
        e.set_footer(text="Gratte propre, reuf. Zéro remboursement si ça gratte le vide.")
        return e

    async def refresh_embed(self, storage) -> None:
        """⚠️ helper maison — ne pas appeler _refresh (réservé par discord.py)."""
        if self.message:
            await self.message.edit(embed=self._base_embed(storage), view=self)

    # ── Widgets
    @discord.ui.select(
        placeholder="Choisis ton ticket…",
        options=[
            discord.SelectOption(label=TICKETS[k]["name"], value=k, description=fmt_eur(TICKETS[k]["price"]) )
            for k in TICKETS
        ],
        custom_id="tabac_select"
    )
    async def select_ticket(self, inter: Interaction, select: discord.ui.Select):
        if not await self._guard(inter): return
        self.current_key = select.values[0]
        await inter.response.defer()
        await self.refresh_embed(inter.client.storage)

    @discord.ui.button(label="🎫 Gratter", style=discord.ButtonStyle.success, custom_id="tabac_gratter")
    async def btn_gratter(self, inter: Interaction, _: discord.ui.Button):
        if not await self._guard(inter): return
        storage = inter.client.storage

        # anti-spam léger
        ok_cd, msg_cd = _touch_cooldown(storage, inter.user.id)
        if not ok_cd:
            await inter.response.send_message(msg_cd or "⏳ Attends un peu.", ephemeral=True)
            return

        if self._locked:
            await inter.response.send_message("⏳ Déjà en train de gratter…", ephemeral=True)
            return
        self._locked = True

        ticket = TICKETS[self.current_key]
        price = int(ticket["price"])
        money_before = _get_money(storage, inter.user.id)
        if money_before < price:
            self._locked = False
            await inter.response.send_message(
                f"💸 Il te manque **{fmt_eur(price - money_before)}** pour ce ticket.",
                ephemeral=True
            )
            return

        # débit
        if not _try_spend(storage, inter.user.id, price):
            self._locked = False
            await inter.response.send_message("💳 Paiement refusé, reviens avec des biftons.", ephemeral=True)
            return

        # Animation de grattage
        cover = "▩"  # tu peux essayer "░", "▒", "▩"
        rows = [
            [cover, cover, cover],
            [cover, cover, cover],
            [cover, cover, cover],
        ]
        symbols_pool = ["🍀", "⭐", "💎", "7️⃣", "🧧"]
        # résultat de “gain”
        gain_cents = _weight_pick(ticket["pool"])

        # Règle simple d’affichage : si gain>0, on force au moins 3 symboles identiques sur une ligne
        if gain_cents > 0:
            sym = random.choice(symbols_pool)
            line = random.randrange(3)
            rows[line] = [sym, sym, sym]
            # remplit le reste aléatoirement
            for r in range(3):
                for c in range(3):
                    if rows[r][c] == cover:
                        rows[r][c] = random.choice(symbols_pool)
        else:
            # tout aléatoire (perdant)
            rows = [[random.choice(symbols_pool) for _ in range(3)] for __ in range(3)]

        # 1) message initial
        e = self._base_embed(storage)
        e.add_field(
            name="Carte",
            value="```\n" + "\n".join(" ".join(row if isinstance(row, list) else row) for row in [["▩ ▩ ▩"],["▩ ▩ ▩"],["▩ ▩ ▩"]]) + "\n```",
            inline=False
        )
        await inter.response.send_message(embed=e)
        msg = await inter.original_response()

        # 2) 3 révélations progressives
        for step in range(3):
            await asyncio.sleep(0.8)
            reveal = []
            for r in range(3):
                line = []
                for c in range(3):
                    # révèle colonne par colonne
                    line.append(rows[r][c] if c <= step else cover)
                reveal.append(" ".join(line))
            e = self._base_embed(storage)
            e.add_field(name="Carte", value="```\n" + "\n".join(reveal) + "\n```", inline=False)
            await msg.edit(embed=e)

        # 3) résultat & crédit éventuel
        if hasattr(storage, "increment_stat"):
            storage.increment_stat(inter.user.id, "tabac_count", 1)

        final_money = _add_money(storage, inter.user.id, gain_cents)  # si 0 => no-op

        res_text = (
            f"🎉 **Gagné {fmt_eur(gain_cents)} !**" if gain_cents > 0
            else "😬 Rien du tout… la chance reviendra."
        )
        e = self._base_embed(storage)
        e.add_field(
            name="Carte",
            value="```\n" + "\n".join(" ".join(row) for row in rows) + "\n```",
            inline=False
        )
        e.add_field(
            name="Résultat",
            value=f"{res_text}\n**Solde**: {fmt_eur(final_money)}",
            inline=False
        )
        await msg.edit(embed=e)

        self._locked = False

    async def on_timeout(self) -> None:
        # À la fin, on désactive tout
        for child in self.children:
            if hasattr(child, "disabled"):
                child.disabled = True
        if self.message:
            try:
                e = discord.Embed(
                    description="⏳ Le kiosque a fermé. Rouvre /tabac pour rejouer.",
                    color=discord.Color.dark_grey()
                )
                await self.message.edit(embed=e, view=None)
            except discord.NotFound:
                pass


# ───────────────────────────────────────────────────────────────────
# Commande
# ───────────────────────────────────────────────────────────────────
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