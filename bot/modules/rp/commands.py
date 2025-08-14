from __future__ import annotations
import random, discord
from discord import app_commands, Interaction, Embed

def setup_rp(tree: app_commands.CommandTree, storage, guild_id: int):
    guild_obj = discord.Object(id=guild_id) if guild_id else None

    @tree.command(name="start", description="Entrer dans LaRue")
    @app_commands.guilds(guild_obj) if guild_obj else (lambda f: f)
    async def start(inter: Interaction):
        p = storage.get_player(inter.user.id)
        if p.get("has_started"):
            await inter.response.send_message("Tu es déjà dans LaRue.", ephemeral=True)
            return
        storage.update_player(inter.user.id, has_started=True, money=0)
        e = Embed(title="Bienvenue dans LaRue",
                  description="Tu as 0€ et un vieux carton. Choisis 1 à 2 actions par jour.")
        await inter.response.send_message(embed=e, ephemeral=False)

    @tree.command(name="mendier", description="Petit revenu")
    @app_commands.guilds(guild_obj) if guild_obj else (lambda f: f)
    async def mendier(inter: Interaction):
        p = storage.get_player(inter.user.id)
        if not p.get("has_started"):
            await inter.response.send_message("Utilise /start avant.", ephemeral=False)
            return
        gain = random.randint(1, 8)
        pp = storage.add_money(inter.user.id, gain)
        await inter.response.send_message(f"On te file {gain}€. Total {pp['money']}€", ephemeral=False)

    @tree.command(name="fouiller", description="Fouiller une poubelle")
    @app_commands.guilds(guild_obj) if guild_obj else (lambda f: f)
    async def fouiller(inter: Interaction):
        p = storage.get_player(inter.user.id)
        if not p.get("has_started"):
            await inter.response.send_message("Utilise /start avant.", ephemeral=False)
            return
        r = random.random()
        if r < 0.6:
            gain = random.randint(2, 15)
            pp = storage.add_money(inter.user.id, gain)
            msg = f"Quelques pièces: +{gain}€. Total {pp['money']}€"
        elif r < 0.9:
            msg = "Un rat t’attaque. Pas de gain."
        else:
            perte = min(5, p["money"])
            pp = storage.update_player(inter.user.id, money=p["money"] - perte)
            msg = f"Tu glisses dans un jus louche. -{perte}€. Total {pp['money']}€"
        await inter.response.send_message(msg, ephemeral=False)