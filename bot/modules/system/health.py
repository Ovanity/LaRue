from __future__ import annotations
import discord
from discord import app_commands, Interaction

def setup_system(tree: app_commands.CommandTree, storage, guild_id: int):
    def scope(func):
        return app_commands.guilds(discord.Object(id=guild_id))(func) if guild_id else func

    @scope
    @tree.command(name="ping", description="Latence")
    async def ping(inter: Interaction):
        await inter.response.send_message("Pong", ephemeral=True)

    @scope
    @tree.command(name="stats", description="Tes stats")
    async def stats(inter: Interaction):
        p = storage.get_player(inter.user.id)
        await inter.response.send_message(f"💼 Argent: {p['money']}€", ephemeral=True)