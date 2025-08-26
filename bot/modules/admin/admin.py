from __future__ import annotations
import discord
from discord import app_commands, Interaction

from bot.domain import admin as d_admin

# Remplace par TON ID Discord
ADMIN_ID = 298893605613862912

admin = app_commands.Group(name="admin", description="Outils d'administration")

# /admin reset scope:<players|cooldowns|inventory|all>
@admin.command(name="reset", description="Réinitialise des tables (joueurs, cooldowns, inventaire ou tout).")
@app_commands.choices(scope=[
    app_commands.Choice(name="players",   value="players"),
    app_commands.Choice(name="cooldowns", value="cooldowns"),
    app_commands.Choice(name="inventory", value="inventory"),
    app_commands.Choice(name="all",       value="all"),
])
async def admin_reset(inter: Interaction, scope: app_commands.Choice[str]):
    if inter.user.id != ADMIN_ID:
        await inter.response.send_message("❌ Accès refusé.", ephemeral=True)
        return

    choice = scope.value
    done: list[str] = []

    try:
        if choice in ("players", "all"):
            d_admin.reset_players()
            done.append("players vidé")
        if choice in ("cooldowns", "all"):
            d_admin.reset_actions()
            done.append("actions (cooldowns) vidée")
        if choice in ("inventory", "all"):
            d_admin.reset_inventory()
            done.append("inventory vidée")

        if not done:
            await inter.response.send_message("⚠️ Rien à faire (choix invalide ?)", ephemeral=True)
        else:
            await inter.response.send_message("✅ " + " • ".join(done), ephemeral=True)

    except Exception as e:
        await inter.response.send_message(f"⚠️ Erreur: {e}", ephemeral=True)


def register(tree: app_commands.CommandTree, guild_obj: discord.Object | None, client: discord.Client | None = None):
    # le client ne sert pas ici; module inscrit en test-only via client.py
    if guild_obj:
        tree.add_command(admin, guild=guild_obj)
    else:
        tree.add_command(admin)

# Compat
def setup_admin(tree: app_commands.CommandTree, guild_obj: discord.Object | None):
    register(tree, guild_obj, None)
