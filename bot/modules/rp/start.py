from __future__ import annotations
import discord
from discord import app_commands, Interaction, Embed

WELCOME_MESSAGE = """
🖥️ **Bienvenue dans LaRue.exe**

Wesh mon reuf, t’es arrivé ici sans thunes, sans matos, et avec un vieux carton troué.  
Trop tard, t’es déjà dans la sauce.

💡 **Règles du game :**
- Tu veux graille ? Tu mendies 🥖
- Tu veux du matos ? Tu fouilles 🗑️
- Tu veux survivre ? Tu bouges vite et tu fermes ta grande bouche

Bonne chance… tu vas en avoir besoin.
"""


class StartView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # Pas de timeout pour que les boutons restent
        self.add_item(discord.ui.Button(label="🥖 Mendier", style=discord.ButtonStyle.primary, custom_id="mendier"))
        self.add_item(discord.ui.Button(label="🗑️ Fouiller", style=discord.ButtonStyle.success, custom_id="fouiller"))
        self.add_item(discord.ui.Button(label="📊 Stats", style=discord.ButtonStyle.secondary, custom_id="stats"))

    @discord.ui.button(label="🥖 Mendier", style=discord.ButtonStyle.primary, custom_id="mendier")
    async def mendier(self, inter: Interaction, button: discord.ui.Button):
        await inter.response.send_message("Tu tends la main… on verra si t’as de la chance.", ephemeral=False)

    @discord.ui.button(label="🗑️ Fouiller", style=discord.ButtonStyle.success, custom_id="fouiller")
    async def fouiller(self, inter: Interaction, button: discord.ui.Button):
        await inter.response.send_message("Tu fouilles dans une poubelle… ça sent la street.", ephemeral=False)

    @discord.ui.button(label="📊 Stats", style=discord.ButtonStyle.secondary, custom_id="stats")
    async def stats(self, inter: Interaction, button: discord.ui.Button):
        storage = inter.client.storage
        p = storage.get_player(inter.user.id)
        if not p or not p.get("has_started"):
            await inter.response.send_message("🛑 Lance /start d’abord, mon reuf.", ephemeral=True)
            return
        await inter.response.send_message(f"💼 Argent: {p['money']}€", ephemeral=False)


def setup_start(tree: app_commands.CommandTree, guild_obj: discord.Object | None):
    """Enregistre /start (onboarding) sur un guild précis si fourni, sinon global."""

    @tree.command(name="start", description="Commence ton aventure dans LaRue.exe")
    @app_commands.guilds(guild_obj) if guild_obj else (lambda f: f)
    async def start(inter: Interaction):
        storage = inter.client.storage
        p = storage.get_player(inter.user.id)

        if p and p.get("has_started"):
            await inter.response.send_message(
                "🛑 Mon reuf, t’as déjà lancé LaRue.exe. Pas de deuxième spawn.",
                ephemeral=True
            )
            return

        storage.update_player(inter.user.id, has_started=True, money=0)

        embed = Embed(
            title="Bienvenue dans LaRue.exe",
            description=WELCOME_MESSAGE,
            color=discord.Color.dark_gray()
        )
        embed.set_footer(text="Choisis une action pour commencer")

        await inter.response.send_message(embed=embed, view=StartView(), ephemeral=False)