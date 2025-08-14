from __future__ import annotations
import discord
from discord import app_commands, Interaction

def setup_system(tree: app_commands.CommandTree, storage, guild_id: int):
    guild_obj = discord.Object(id=guild_id) if guild_id else None

    @tree.command(name="ping", description="Latence")
    @app_commands.guilds(guild_obj) if guild_obj else (lambda f: f)
    async def ping(inter: Interaction):
        await inter.response.send_message("Pong", ephemeral=True)

    @tree.command(name="stats", description="Tes stats")
    @app_commands.guilds(guild_obj) if guild_obj else (lambda f: f)
    async def stats(inter: Interaction):
        p = storage.get_player(inter.user.id)

        # Si aucun joueur trouvé ou pas encore démarré l'aventure
        if not p or not p.get("has_started"):
            await inter.response.send_message(
                "🚀 Tu n'as pas encore commencé ton aventure. Utilise **/start** pour débuter !",
                ephemeral=True
            )
            return

        await inter.response.send_message(
            f"💼 Argent: {p['money']}€",
            ephemeral=False
        )