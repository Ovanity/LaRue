from __future__ import annotations
import discord
from discord import app_commands, Interaction, Embed

# on réutilise les mêmes fonctions que les slash
from bot.modules.rp.economy import mendier_action, fouiller_action, stats_action

# Palette de couleurs (on en choisit une selon l'utilisateur)
PALETTE = [
    discord.Color.blurple(),
    discord.Color.dark_teal(),
    discord.Color.dark_gold(),
    discord.Color.purple(),
    discord.Color.dark_orange(),
]

WELCOME_TITLE = "🌆 **Bienvenue dans LaRue.exe**"
WELCOME_INTRO = (
    "🖥️ **Mode Survie Activé**\n"
    "Wesh mon reuf, t’es arrivé ici **sans thunes**, sans matos, et avec un vieux carton.\n"
    "T’es direct dans **la sauce**."
)
WELCOME_RULES = (
    "📜 **Règles du terrain**\n"
    "💰 Tu veux graille ? → *Tu mendies*\n"
    "🗑️ Tu veux du matos ? → *Tu fouilles*\n"
    "🏃 Tu veux survivre ? → *Tu bouges vite*"
)
WELCOME_HINTS = (
    "▶️ Utilise les **boutons** ci‑dessous pour agir tout de suite\n"
    "ou tape : `/hesshelp` • pour avoir plus d'informations.\n"
)

class StartView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=120)  # 120s d'activité
        self.owner_id = owner_id
        self.message: discord.Message | None = None  # rempli après envoi

    async def _guard(self, inter: Interaction) -> bool:
        if inter.user.id != self.owner_id:
            await inter.response.send_message(
                "🛑 Ce menu n'est pas à toi mon reuf, tu joues à quoi ?",
                ephemeral=True
            )
            return False
        return True

    async def on_timeout(self) -> None:
        """Désactive les boutons et marque l'embed comme expiré."""
        if not self.message:
            return
        try:
            # clone l'embed existant
            old = self.message.embeds[0] if self.message.embeds else None
            if old:
                new_embed = discord.Embed.from_dict(old.to_dict())
                new_embed.color = discord.Color.dark_grey()
                new_embed.set_footer(text="⏳ Ce menu est expiré, il fallait se bouger mon reuf.")
                # désactive tous les boutons
                self.disable_all_items()
                await self.message.edit(embed=new_embed, view=self)
            else:
                self.disable_all_items()
                await self.message.edit(view=self)
        except discord.NotFound:
            pass  # déjà supprimé ailleurs

    @discord.ui.button(label="🥖 Mendier", style=discord.ButtonStyle.primary, custom_id="start_mendier")
    async def btn_mendier(self, inter: Interaction, _: discord.ui.Button):
        if not await self._guard(inter):
            return
        storage = inter.client.storage
        p = storage.get_player(inter.user.id)
        if not p.get("has_started"):
            await inter.response.send_message("🛑 Lance /start d’abord.", ephemeral=True)
            return
        res = mendier_action(storage, inter.user.id)
        await inter.response.send_message(res["msg"])

    @discord.ui.button(label="🗑️ Fouiller", style=discord.ButtonStyle.success, custom_id="start_fouiller")
    async def btn_fouiller(self, inter: Interaction, _: discord.ui.Button):
        if not await self._guard(inter):
            return
        storage = inter.client.storage
        p = storage.get_player(inter.user.id)
        if not p.get("has_started"):
            await inter.response.send_message("🛑 Lance /start d’abord.", ephemeral=True)
            return
        res = fouiller_action(storage, inter.user.id)
        await inter.response.send_message(res["msg"])

    @discord.ui.button(label="📊 Stats", style=discord.ButtonStyle.secondary, custom_id="start_stats")
    async def btn_stats(self, inter: Interaction, _: discord.ui.Button):
        if not await self._guard(inter):
            return
        storage = inter.client.storage
        p = storage.get_player(inter.user.id)
        if not p or not p.get("has_started"):
            await inter.response.send_message("🛑 Lance /start d’abord.", ephemeral=True)
            return
        await inter.response.send_message(stats_action(storage, inter.user.id))

def register(tree: app_commands.CommandTree, guild_obj: discord.Object | None, client: discord.Client):
    @tree.command(name="start", description="Commence ton aventure dans LaRue.exe")
    @app_commands.guilds(guild_obj) if guild_obj else (lambda f: f)
    async def start(inter: Interaction):
        storage = client.storage
        p = storage.get_player(inter.user.id)

        if p and p.get("has_started"):
            await inter.response.send_message(
                "🛑 Mon reuf, t’as déjà lancé LaRue.exe. Pas de deuxième spawn.",
                ephemeral=True
            )
            return

        storage.update_player(inter.user.id, has_started=True, money=0)

        # Couleur choisie selon l'utilisateur (stable mais variée)
        color = PALETTE[inter.user.id % len(PALETTE)]

        embed = Embed(title=WELCOME_TITLE, color=color)

        # Une seule colonne claire + espace entre sections
        embed.add_field(
            name="Introduction",
            value=WELCOME_INTRO + "\n\u200b",
            inline=False
        )
        embed.add_field(
            name="Code de LaRue.exe",
            value=WELCOME_RULES + "\n\u200b",
            inline=False
        )
        embed.add_field(
            name="Tips",
            value=WELCOME_HINTS,
            inline=False
        )
        embed.set_footer(text="Choisis une action pour commencer • LaRue.exe")

        # Envoi + enregistrement du message pour le timeout
        view = StartView(inter.user.id)
        await inter.response.send_message(embed=embed, view=view, ephemeral=False)
        view.message = await inter.original_response()