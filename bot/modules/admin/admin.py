from __future__ import annotations
import os
import sqlite3
import discord
from discord import app_commands, Interaction

# Remplace par TON ID Discord
ADMIN_ID = 298893605613862912

admin = app_commands.Group(name="admin", description="Outils d'administration")

@admin.command(name="reset", description="Réinitialise la base de données (table players).")
async def admin_reset(inter: Interaction):
    if inter.user.id != ADMIN_ID:
        await inter.response.send_message("❌ Accès refusé.", ephemeral=True)
        return

    storage = inter.client.storage

    try:
        # Cas SQLiteStorage (on a un attribut db_path)
        if hasattr(storage, "db_path"):
            db_path = str(storage.db_path)
            con = sqlite3.connect(db_path)
            with con:
                con.execute("DELETE FROM players;")
            msg = f"✅ players vidé dans {db_path}"
        else:
            # Fallback JSONStorage si jamais tu repasses en JSON
            if hasattr(storage, "path"):
                storage.path.write_text("{}")
                msg = f"✅ players.json réinitialisé ({storage.path})"
            else:
                msg = "⚠️ Backend inconnu: rien fait."

        await inter.response.send_message(msg, ephemeral=True)
    except Exception as e:
        await inter.response.send_message(f"⚠️ Erreur: {e}", ephemeral=True)

def setup_admin(tree: app_commands.CommandTree, guild_obj: discord.Object | None):
    # Attache le groupe /admin (scopé guild si fourni)
    if guild_obj:
        tree.add_command(admin, guild=guild_obj)
    else:
        tree.add_command(admin)