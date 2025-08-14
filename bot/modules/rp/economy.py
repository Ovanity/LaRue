from __future__ import annotations
import random
import discord
from discord import app_commands, Interaction

def setup_economy(tree: app_commands.CommandTree, guild_obj: discord.Object | None):
    # Déclare un groupe /ruelle
    ruelle = app_commands.Group(
        name="ruelle",
        description="La débrouille: mendier, fouiller, survivre."
    )

    @ruelle.command(name="mendier", description="Gagne quelques pièces")
    async def mendier(inter: Interaction):
        storage = inter.client.storage
        p = storage.get_player(inter.user.id)
        if not p.get("has_started"):
            await inter.response.send_message("Utilise /start avant.")
            return
        gain = random.randint(1, 8)
        if hasattr(storage, "add_money"):
            pp = storage.add_money(inter.user.id, gain)
        else:
            pp = storage.update_player(inter.user.id, money=p["money"] + gain)
        await inter.response.send_message(f"Tu tends la main… +{gain}€. Total {pp['money']}€")

    @ruelle.command(name="fouiller", description="Fouille une poubelle")
    async def fouiller(inter: Interaction):
        storage = inter.client.storage
        p = storage.get_player(inter.user.id)
        if not p.get("has_started"):
            await inter.response.send_message("Utilise /start avant.")
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
            msg = "Un rat t’attaque. Pas de gain."
        else:
            perte = min(5, p["money"])
            pp = storage.update_player(inter.user.id, money=p["money"] - perte)
            msg = f"Tu glisses dans un jus louche. -{perte}€. Total {pp['money']}€"

        await inter.response.send_message(msg)

    # Enregistrer le groupe sur le tree (scopé guild si fourni)
    if guild_obj:
        tree.add_command(ruelle, guild=guild_obj)
    else:
        tree.add_command(ruelle)