from __future__ import annotations
import discord
from discord import app_commands, Interaction, Embed

# on réutilise les mêmes fonctions que les slash
from bot.modules.rp.economy import mendier_action, fouiller_action, stats_action

WELCOME_MESSAGE = """
╔══════════════════════╗
   🖥️ **Mode Survie Activé**
╚══════════════════════╝

👋 **Wesh mon reuf**
T’es arrivé ici **sans thunes**, sans matos, et avec un vieux carton.
Pas de tuto, pas de cinématique — c’est **direct dans le dur**.

📜 **Règles du terrain**
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
💰 Tu veux graille ? → *Tu mendies*
🗑️ Tu veux du matos ? → *Tu fouilles*
🏃 Tu veux survivre ? → *Tu bouges vite*
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

🔥 Bonne chance, soldat de LaRue.
"""

class StartView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=120)
        self.owner_id = owner_id

    async def _guard(self, inter: Interaction) -> bool:
        if inter.user.id != self.owner_id:
            await inter.response.send_message("🛑 Ce menu n'est pas à toi mon reuf, tu joues à quoi ?", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="🥖 Mendier", style=discord.ButtonStyle.primary, custom_id="start_mendier")
    async def btn_mendier(self, inter: Interaction, _: discord.ui.Button):
        if not await self._guard(inter): return
        storage = inter.client.storage
        p = storage.get_player(inter.user.id)
        if not p.get("has_started"):
            await inter.response.send_message("🛑 Lance /start d’abord.", ephemeral=True)
            return
        res = mendier_action(storage, inter.user.id)
        await inter.response.send_message(res["msg"])

    @discord.ui.button(label="🗑️ Fouiller", style=discord.ButtonStyle.success, custom_id="start_fouiller")
    async def btn_fouiller(self, inter: Interaction, _: discord.ui.Button):
        if not await self._guard(inter): return
        storage = inter.client.storage
        p = storage.get_player(inter.user.id)
        if not p.get("has_started"):
            await inter.response.send_message("🛑 Lance /start d’abord.", ephemeral=True)
            return
        res = fouiller_action(storage, inter.user.id)
        await inter.response.send_message(res["msg"])

    @discord.ui.button(label="📊 Stats", style=discord.ButtonStyle.secondary, custom_id="start_stats")
    async def btn_stats(self, inter: Interaction, _: discord.ui.Button):
        if not await self._guard(inter): return
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
            await inter.response.send_message("🛑 Mon reuf, t’as déjà lancé LaRue.exe. Pas de deuxième spawn.", ephemeral=True)
            return

        storage.update_player(inter.user.id, has_started=True, money=0)

        embed = Embed(
            title="🌆 **Bienvenue dans LaRue.exe**",
            description=WELCOME_MESSAGE,
            color=discord.Color.blurple()
        )
        embed.set_footer(text="Choisis une action pour commencer")
        await inter.response.send_message(embed=embed, view=StartView(inter.user.id), ephemeral=False)