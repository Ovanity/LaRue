import discord
from discord import app_commands
from discord.ext import commands
import sqlite3
import os

from bot.config import settings  # pour récupérer settings.data_dir

# Ton ID Discord (remplace par le tien)
ADMIN_ID = 298893605613862912

def setup_admin(tree: app_commands.CommandTree, storage, guild_id: int | None):
    guild_kw = {"guild": discord.Object(id=guild_id)} if guild_id else {}

    @tree.command(name="admin_reset", description="⚠️ Réinitialise la base de données", **guild_kw)
    async def admin_reset(interaction: discord.Interaction):
        if interaction.user.id != ADMIN_ID:
            await interaction.response.send_message("❌ Accès refusé", ephemeral=True)
            return

        db_path = os.path.join(settings.data_dir, "larue.db")

        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("DELETE FROM players;")
            conn.commit()
            conn.close()

            await interaction.response.send_message("✅ Base de données réinitialisée.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"⚠️ Erreur : {e}", ephemeral=True)