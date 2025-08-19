from __future__ import annotations
import discord
from discord import app_commands, Interaction, Embed

# ——— Actions & constantes depuis economy (source de vérité)
from bot.modules.rp.economy import (
    mendier_action, fouiller_action, poches_action,
    MENDIER_COOLDOWN_S, MENDIER_DAILY_CAP,
    FOUILLER_COOLDOWN_S, FOUILLER_DAILY_CAP,
)

# Vérif des limites (alias public si dispo)
try:
    from bot.modules.rp.economy import check_limit
except Exception:
    from bot.modules.rp.economy import _check_limit as check_limit

# Emoji & format monnaie
from bot.modules.common.money import MONEY_EMOJI, fmt_eur

START_MONEY_CENTS = 100  # 1 BiffCoin

# ── Palette
PALETTE = [
    discord.Color.blurple(),
    discord.Color.dark_teal(),
    discord.Color.dark_gold(),
    discord.Color.purple(),
    discord.Color.dark_orange(),
]

# ── Texte (compact, sans titres internes redondants)
WELCOME_INTRO = (
    "🌆 **Bienvenue dans LaRue.exe**\n"
    "{mention}, ici tout se compte en **BiffCoins {emoji}**. "
    "Tu ramasses **{start}** par terre — cadeau de bienvenue.\n"
    "Commence léger, finis chargé."
)

WELCOME_RULES = (
    "🥖 Mendier — petits gains (1/h)\n"
    "🗑️ Fouiller — une fouille (1/j)\n"
    "🎟️ Tabac — tickets à gratter\n"
    "🛒 Shop — boosts utiles\n"
    "🪪 Profil — bio & respect\n"
    "💸 Poches — ton capital"
)

WELCOME_HINTS = (
    "▶️ Clique un bouton pour commencer. "
    "Astuce : tente ta chance au tabac. "
    "Besoin d’aide ? `/LRHelp`"
)

# ─────────────────────────────
# Vue de démarrage
# ─────────────────────────────
class StartView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=120)
        self.owner_id = owner_id
        self.message: discord.Message | None = None

    async def _guard(self, inter: Interaction) -> bool:
        if inter.user.id != self.owner_id:
            await inter.response.send_message("🛑 Ce menu n’est pas à toi.", ephemeral=True)
            return False
        return True

    async def _expire_menu(self) -> None:
        """Ferme le menu après la 1ère action réussie (anti-clutter)."""
        if not self.message:
            return
        try:
            expired = discord.Embed(
                description="✅ Session lancée. Menu fermé pour éviter le spam.",
                color=discord.Color.dark_grey()
            )
            await self.message.edit(embed=expired, view=None)
            self.stop()
        except discord.NotFound:
            pass

    async def on_timeout(self) -> None:
        if not self.message:
            return
        try:
            expired = discord.Embed(
                description="⏳ Ce menu est expiré.",
                color=discord.Color.dark_grey()
            )
            await self.message.edit(embed=expired, view=None)
            self.stop()
        except discord.NotFound:
            pass

    @discord.ui.button(label="🥖 Mendier", style=discord.ButtonStyle.primary, custom_id="start_mendier")
    async def btn_mendier(self, inter: Interaction, _: discord.ui.Button):
        if not await self._guard(inter):
            return
        storage = inter.client.storage
        p = storage.get_player(inter.user.id)
        if not p.get("has_started"):
            await inter.response.send_message("🛑 Lance /start d’abord.", ephemeral=True)
            return

        ok, msg = check_limit(storage, inter.user.id, "mendier", MENDIER_COOLDOWN_S, MENDIER_DAILY_CAP)
        if not ok:
            await inter.response.send_message(msg, ephemeral=True)
            return

        res = mendier_action(storage, inter.user.id)
        await inter.response.send_message(res["msg"])
        await self._expire_menu()

    @discord.ui.button(label="🗑️ Fouiller", style=discord.ButtonStyle.success, custom_id="start_fouiller")
    async def btn_fouiller(self, inter: Interaction, _: discord.ui.Button):
        if not await self._guard(inter):
            return
        storage = inter.client.storage
        p = storage.get_player(inter.user.id)
        if not p.get("has_started"):
            await inter.response.send_message("🛑 Lance /start d’abord.", ephemeral=True)
            return

        ok, msg = check_limit(storage, inter.user.id, "fouiller", FOUILLER_COOLDOWN_S, FOUILLER_DAILY_CAP)
        if not ok:
            await inter.response.send_message(msg, ephemeral=True)
            return

        res = fouiller_action(storage, inter.user.id)
        await inter.response.send_message(res["msg"])
        await self._expire_menu()

    @discord.ui.button(label="💸 Poches", style=discord.ButtonStyle.secondary, custom_id="start_poches")
    async def btn_poches(self, inter: Interaction, _: discord.ui.Button):
        if not await self._guard(inter):
            return
        storage = inter.client.storage
        p = storage.get_player(inter.user.id)
        if not p or not p.get("has_started"):
            await inter.response.send_message("🛑 Lance /start d’abord.", ephemeral=True)
            return
        embed = poches_action(storage, inter.user.id)  # Embed direct
        await inter.response.send_message(embed=embed, ephemeral=False)
        await self._expire_menu()

# ─────────────────────────────
# Commande /start
# ─────────────────────────────
def register(tree: app_commands.CommandTree, guild_obj: discord.Object | None, client: discord.Client):
    @tree.command(name="start", description="Commence ton aventure dans LaRue.exe")
    @app_commands.guilds(guild_obj) if guild_obj else (lambda f: f)
    async def start(inter: Interaction):
        storage = client.storage
        p = storage.get_player(inter.user.id)

        if p and p.get("has_started"):
            await inter.response.send_message("🛑 Tu as déjà lancé LaRue.exe.", ephemeral=True)
            return

        # Créditer au moins 1 BiffCoin au premier démarrage
        initial = max(int(p.get("money", 0)) if p else 0, START_MONEY_CENTS)
        storage.update_player(inter.user.id, has_started=True, money=initial)

        color = PALETTE[inter.user.id % len(PALETTE)]
        embed = Embed(title="🌆 LaRue.exe", color=color)

        embed.add_field(
            name="Introduction",
            value=WELCOME_INTRO.format(
                mention=inter.user.mention,
                emoji=MONEY_EMOJI,
                start=fmt_eur(START_MONEY_CENTS),
            ),
            inline=False
        )
        embed.add_field(name="Actions", value=WELCOME_RULES, inline=False)
        embed.add_field(name="Tips", value=WELCOME_HINTS, inline=False)
        embed.set_footer(text="Choisis une action pour commencer • LaRue.exe")

        view = StartView(inter.user.id)
        await inter.response.send_message(embed=embed, view=view, ephemeral=False)
        view.message = await inter.original_response()