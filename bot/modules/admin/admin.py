from __future__ import annotations
import os
import sqlite3
import discord
from discord import app_commands, Interaction

# Remplace par TON ID Discord
ADMIN_ID = 298893605613862912

admin = app_commands.Group(name="admin", description="Outils d'administration")

# /admin reset scope:<players|cooldowns|all>
@admin.command(name="reset", description="Réinitialise la base (joueurs, cooldowns ou tout).")
@app_commands.choices(scope=[
    app_commands.Choice(name="players", value="players"),
    app_commands.Choice(name="cooldowns", value="cooldowns"),
    app_commands.Choice(name="all", value="all"),
])
async def admin_reset(inter: Interaction, scope: app_commands.Choice[str]):
    if inter.user.id != ADMIN_ID:
        await inter.response.send_message("❌ Accès refusé.", ephemeral=True)
        return

    storage = inter.client.storage
    choice = scope.value

    def _ok(msg: str):
        return inter.response.send_message(f"✅ {msg}", ephemeral=True)

    def _warn(msg: str):
        return inter.response.send_message(f"⚠️ {msg}", ephemeral=True)

    try:
        # Backend SQLite
        if hasattr(storage, "db_path"):
            db_path = str(storage.db_path)

            def _count(con, table: str) -> int:
                cur = con.execute(f"SELECT COUNT(*) FROM {table};")
                (n,) = cur.fetchone()
                return int(n)

            con = sqlite3.connect(db_path)
            with con:
                msg_parts = []
                if choice in ("players", "all"):
                    n = _count(con, "players")
                    con.execute("DELETE FROM players;")
                    msg_parts.append(f"players vidé ({n} ligne(s))")
                if choice in ("cooldowns", "all"):
                    # table des limites (cooldowns/quotas)
                    # existe grâce à ton storage._init_db()
                    n = _count(con, "actions")
                    con.execute("DELETE FROM actions;")
                    msg_parts.append(f"actions (cooldowns) vidée ({n} ligne(s))")

            await _ok(f"{' & '.join(msg_parts)} dans {db_path}")

        # Fallback JSON (si jamais tu repasses en JSONStorage)
        elif hasattr(storage, "path"):
            if choice in ("players", "all"):
                storage.path.write_text("{}")
                remain = " (cooldowns non gérés en JSON)" if choice == "all" else ""
                await _ok(f"players.json réinitialisé ({storage.path}){remain}")
            elif choice == "cooldowns":
                await _warn("Pas de table cooldowns avec le backend JSON.")
        else:
            await _warn("Backend de données inconnu : aucune action.")

    except Exception as e:
        await inter.response.send_message(f"⚠️ Erreur: {e}", ephemeral=True)


def setup_admin(tree: app_commands.CommandTree, guild_obj: discord.Object | None):
    # Attache le groupe /admin (scopé guild si fourni)
    if guild_obj:
        tree.add_command(admin, guild=guild_obj)
    else:
        tree.add_command(admin)