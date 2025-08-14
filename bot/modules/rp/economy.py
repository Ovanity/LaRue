from __future__ import annotations
import random
import discord
from discord import app_commands, Interaction

# ─────────────────────────────
# Actions réutilisables (pour start.py et slash)
# ─────────────────────────────

def mendier_action(storage, user_id: int) -> dict:
    p = storage.get_player(user_id)
    gain = random.randint(1, 8)
    if hasattr(storage, "add_money"):
        pp = storage.add_money(user_id, gain)
    else:
        pp = storage.update_player(user_id, money=p["money"] + gain)
    return {
        "money": pp["money"],
        "delta": gain,
        "msg": f"Tu tends la main… +{gain}€ • Total {pp['money']}€",
    }

def fouiller_action(storage, user_id: int) -> dict:
    p = storage.get_player(user_id)
    r = random.random()
    if r < 0.6:
        gain = random.randint(2, 15)
        if hasattr(storage, "add_money"):
            pp = storage.add_money(user_id, gain)
        else:
            pp = storage.update_player(user_id, money=p["money"] + gain)
        return {"money": pp["money"], "delta": gain, "msg": f"Quelques pièces: +{gain}€ • Total {pp['money']}€"}
    elif r < 0.9:
        return {"money": p["money"], "delta": 0, "msg": "Rien d’intéressant."}
    else:
        perte = min(5, p["money"])
        pp = storage.update_player(user_id, money=max(0, p["money"] - perte))
        return {"money": pp["money"], "delta": -perte, "msg": f"Tu glisses, ça tourne mal. -{perte}€ • Total {pp['money']}€"}

def stats_action(storage, user_id: int) -> str:
    p = storage.get_player(user_id)
    if not p or not p.get("has_started"):
        return "🚀 Tu n'as pas encore commencé ton aventure. Utilise **/start** pour débuter !"
    return f"💼 Argent: {p['money']}€"


# ─────────────────────────────
# Enregistrement des commandes
# ─────────────────────────────

def _build_group() -> app_commands.Group:
    return app_commands.Group(
        name="hess",
        description="La débrouille: mendier, fouiller, survivre."
    )

def register(tree: app_commands.CommandTree, guild_obj: discord.Object | None, client: discord.Client | None = None):
    """
    Enregistre les commandes slash /hess mendier, /hess fouiller et /stats.
    """
    hess = _build_group()

    @hess.command(name="mendier", description="Gagne quelques pièces")
    async def mendier(inter: Interaction):
        storage = inter.client.storage
        p = storage.get_player(inter.user.id)
        if not p.get("has_started"):
            await inter.response.send_message("Utilise /start avant.")
            return
        res = mendier_action(storage, inter.user.id)
        await inter.response.send_message(res["msg"])

    @hess.command(name="fouiller", description="Fouille une poubelle")
    async def fouiller(inter: Interaction):
        storage = inter.client.storage
        p = storage.get_player(inter.user.id)
        if not p.get("has_started"):
            await inter.response.send_message("Utilise /start avant.")
            return
        res = fouiller_action(storage, inter.user.id)
        await inter.response.send_message(res["msg"])

    # Ancien /stats déplacé ici
    @tree.command(name="stats", description="Tes stats")
    @app_commands.guilds(guild_obj) if guild_obj else (lambda f: f)
    async def stats(inter: Interaction):
        storage = inter.client.storage
        p = storage.get_player(inter.user.id)
        msg = stats_action(storage, inter.user.id)
        # si pas commencé, rends-le éphémère :
        ephemeral = not (p and p.get("has_started"))
        await inter.response.send_message(msg, ephemeral=ephemeral)

    # Attache le groupe au tree
    if guild_obj:
        tree.add_command(hess, guild=guild_obj)
    else:
        tree.add_command(hess)

# Compat setup
def setup_economy(tree: app_commands.CommandTree, guild_obj: discord.Object | None):
    register(tree, guild_obj, None)