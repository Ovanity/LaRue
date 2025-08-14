from __future__ import annotations
import random
import discord
from discord import app_commands, Interaction, Embed

WELCOME_MESSAGE = """
🖥️ **Bienvenue dans LaRue.exe**

Wesh mon reuf, t’es arrivé ici sans thunes, sans matos, et avec un vieux carton.  
Pas de tuto, pas de cinématique — c’est direct dans le dur.

**Règles:**
- Tu veux graille ? Tu mendies
- Tu veux du matos ? Tu fouilles
- Tu veux survivre ? Tu bouges vite

Bonne chance.
"""

class StartView(discord.ui.View):
    # Vue non persistante (expire au bout de 120s)
    def __init__(self):
        super().__init__(timeout=120)

    @discord.ui.button(label="🥖 Mendier", style=discord.ButtonStyle.primary, custom_id="start_mendier")
    async def btn_mendier(self, inter: Interaction, button: discord.ui.Button):
        storage = inter.client.storage
        p = storage.get_player(inter.user.id)
        if not p.get("has_started"):
            await inter.response.send_message("🛑 Lance /start d’abord.", ephemeral=True)
            return
        gain = random.randint(1, 8)
        if hasattr(storage, "add_money"):
            pp = storage.add_money(inter.user.id, gain)
        else:
            pp = storage.update_player(inter.user.id, money=p["money"] + gain)
        await inter.response.send_message(f"Tu tends la main… +{gain}€. Total {pp['money']}€")

    @discord.ui.button(label="🗑️ Fouiller", style=discord.ButtonStyle.success, custom_id="start_fouiller")
    async def btn_fouiller(self, inter: Interaction, button: discord.ui.Button):
        storage = inter.client.storage
        p = storage.get_player(inter.user.id)
        if not p.get("has_started"):
            await inter.response.send_message("🛑 Lance /start d’abord.", ephemeral=True)
            return
        r = random.random()
        if r < 0.6:
            gain = random.randint(2, 15)
            if hasattr(storage, "add_money"):
                pp = storage.add_money(inter.user.id, gain)
            else:
                pp = storage.update_player(inter.user.id, money=p["money"] + gain)
            msg = f"Quelques pièces: +{gain}€. Total {pp['money']}€"
        elif r < 0.9:
            msg = "Rien d’intéressant."
        else:
            perte = min(5, p["money"])
            pp = storage.update_player(inter.user.id, money=max(0, p['money'] - perte))
            msg = f"Tu glisses, ça tourne mal. -{perte}€. Total {pp['money']}€"
        await inter.response.send_message(msg)

    @discord.ui.button(label="📊 Stats", style=discord.ButtonStyle.secondary, custom_id="start_stats")
    async def btn_stats(self, inter: Interaction, button: discord.ui.Button):
        storage = inter.client.storage
        p = storage.get_player(inter.user.id)
        if not p or not p.get("has_started"):
            await inter.response.send_message("🛑 Lance /start d’abord.", ephemeral=True)
            return
        await inter.response.send_message(f"💼 Argent: {p['money']}€")

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

        # Affiche l’embed + les boutons
        await inter.response.send_message(embed=embed, view=StartView(), ephemeral=False)