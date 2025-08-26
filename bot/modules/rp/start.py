# bot/modules/rp/start.py
from __future__ import annotations
import discord
from discord import app_commands, Interaction, Embed

# Flows depuis economy (déjà full-domain)
from bot.modules.rp.economy import play_mendier, play_fouiller

# Emoji & format monnaie
from bot.modules.common.money import MONEY_EMOJI, fmt_eur

# Domaine
from bot.domain import players as d_players
from bot.domain import economy as d_economy

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

def _embed_poches(user_id: int) -> discord.Embed:
    bal = d_economy.balance(user_id)
    e = Embed(
        description=f"En fouillant tes poches, tu trouves **{fmt_eur(bal)}**.",
        color=discord.Color.dark_gold(),
    )
    e.set_footer(text="Source de vérité : ledger")
    return e

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
        success = await play_mendier(inter)
        if success:
            await self._expire_menu()

    @discord.ui.button(label="🗑️ Fouiller", style=discord.ButtonStyle.success, custom_id="start_fouiller")
    async def btn_fouiller(self, inter: Interaction, _: discord.ui.Button):
        if not await self._guard(inter):
            return
        success = await play_fouiller(inter)
        if success:
            await self._expire_menu()

    @discord.ui.button(label="💸 Poches", style=discord.ButtonStyle.secondary, custom_id="start_poches")
    async def btn_poches(self, inter: Interaction, _: discord.ui.Button):
        if not await self._guard(inter):
            return
        p = d_players.get(inter.user.id)
        if not (p and p.get("has_started")):
            await inter.response.send_message("🛑 Lance **/start** d’abord.", ephemeral=True)
            return
        await inter.response.send_message(embed=_embed_poches(inter.user.id), ephemeral=False)
        await self._expire_menu()

# ─────────────────────────────
# Commande /start
# ─────────────────────────────
def register(tree: app_commands.CommandTree, guild_obj: discord.Object | None, client: discord.Client):
    @tree.command(name="start", description="Commence ton aventure dans LaRue.exe")
    @app_commands.guilds(guild_obj) if guild_obj else (lambda f: f)
    async def start(inter: Interaction):
        p = d_players.get(inter.user.id)

        if p and p.get("has_started"):
            await inter.response.send_message("🛑 Tu as déjà lancé LaRue.exe.", ephemeral=True)
            return

        # Marque le joueur et crédite le cadeau de bienvenue (idempotent)
        d_players.update(inter.user.id, has_started=True)
        d_economy.credit_once(
            inter.user.id,
            START_MONEY_CENTS,
            reason="start.gift",
            idem_key="start:gift",   # clé stable par joueur pour éviter le double-crédit
        )

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
