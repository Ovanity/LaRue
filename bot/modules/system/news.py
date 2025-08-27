from __future__ import annotations
import discord
from discord import app_commands, Interaction
from bot.persistence import events as repo_events

@app_commands.command(name="news", description="Les derniers posts officiels (liens).")
async def news(inter: Interaction):
    items = repo_events.list_recent(3)
    if not items:
        await inter.response.send_message("Rien à signaler pour l’instant.", ephemeral=True); return

    e = discord.Embed(title="📰 LaRue.exe — Derniers posts", color=discord.Color.blurple())
    for ev in items:
        title = ev.get("title") or ev.get("kind") or "Annonce"
        url   = ev.get("jump_url") or ""
        line  = f"[Ouvrir]({url}) — <t:{ev['starts_at']}:R>" if url else f"<t:{ev['starts_at']}:R>"
        e.add_field(name=title, value=line, inline=False)
    await inter.response.send_message(embed=e, ephemeral=True)

def register(tree, guild_obj, client=None):
    if guild_obj:
        tree.add_command(news, guild=guild_obj)
    else:
        tree.add_command(news)
