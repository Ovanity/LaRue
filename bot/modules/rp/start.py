from __future__ import annotations
import discord
from discord import app_commands, Interaction, Embed

def setup_start(tree: app_commands.CommandTree, guild_obj: discord.Object | None):
    """Enregistre /start (onboarding) sur un guild précis si fourni, sinon global."""
    @tree.command(name="start", description="Entrer dans LaRue")
    @app_commands.guilds(guild_obj) if guild_obj else (lambda f: f)
    async def start(inter: Interaction):
        # Accès au storage via client (voir client.py)
        storage = inter.client.storage
        p = storage.get_player(inter.user.id)
        if p.get("has_started"):
            await inter.response.send_message("Tu es déjà dans LaRue.", ephemeral=False)
            return

        storage.update_player(inter.user.id, has_started=True, money=0)
        e = Embed(
            title="Bienvenue dans LaRue",
            description="Tu as 0€ et un vieux carton. Utilise /ruelle mendier|fouiller pour commencer."
        )
        await inter.response.send_message(embed=e, ephemeral=False)