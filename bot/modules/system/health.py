from discord import app_commands, Interaction

def setup_system(tree: app_commands.CommandTree, storage, guild_id: int):
    guild_kw = {"guilds":[guild_id]} if guild_id else {}
    @tree.command(name="ping", description="Latence", **guild_kw)
    async def ping(inter: Interaction):
        await inter.response.send_message("Pong", ephemeral=True)

    @tree.command(name="stats", description="Tes stats", **guild_kw)
    async def stats(inter: Interaction):
        p = storage.get_player(inter.user.id)
        await inter.response.send_message(f"Argent: {p['money']}€", ephemeral=True)
