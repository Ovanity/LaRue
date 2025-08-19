from __future__ import annotations
from typing import Optional
import discord
from discord import app_commands, Interaction
from bot.modules.common.money import fmt_eur

def _color(hexstr: str) -> discord.Color:
    try: return discord.Color(int(hexstr.strip("#"), 16))
    except Exception: return discord.Color.dark_grey()

def _embed_profile(storage, uid: int) -> discord.Embed:
    prof = storage.get_profile(uid)
    player = storage.get_player(uid)
    money = fmt_eur(player["money"])
    e = discord.Embed(
        title=f"🪪 Profil — {prof.get('title') or 'Anonyme du Square'}",
        description=prof.get("bio") or "Aucune bio.",
        color=_color(prof.get("color_hex","FFD166"))
    )
    e.add_field(name="💰 Biftons", value=money, inline=True)
    e.add_field(name="🧿 Street Cred", value=str(int(prof.get("cred",0))), inline=True)
    return e

def register(tree: app_commands.CommandTree, guild_obj: Optional[discord.Object], client: discord.Client | None = None):
    group = app_commands.Group(name="profil", description="Profil social LaRue.exe")

    @group.command(name="voir", description="Afficher un profil")
    @app_commands.describe(user="(optionnel) quelqu’un d’autre")
    async def voir(inter: Interaction, user: Optional[discord.User] = None):
        storage = inter.client.storage
        target = user or inter.user
        await inter.response.send_message(embed=_embed_profile(storage, target.id))

    @group.command(name="set_bio", description="Définir ta bio (160 max)")
    async def set_bio(inter: Interaction, bio: str):
        storage = inter.client.storage
        if len(bio) > 160:
            await inter.response.send_message("❌ 160 caractères max.", ephemeral=True); return
        storage.upsert_profile(inter.user.id, bio=bio.strip())
        await inter.response.send_message("✅ Bio mise à jour.", ephemeral=True)

    @group.command(name="respect", description="Donner +1 Street Cred (1/jour par personne)")
    async def respect(inter: Interaction, user: discord.User):
        if user.id == inter.user.id:
            await inter.response.send_message("😅 Tu peux pas te respecter toi-même.", ephemeral=True); return
        storage = inter.client.storage
        ok, why = storage.can_give_respect(inter.user.id, user.id)
        if not ok:
            await inter.response.send_message(why or "⏳ Demain.", ephemeral=True); return
        new_cred = storage.give_respect(inter.user.id, user.id)
        await inter.response.send_message(f"🤝 Respect donné à {user.mention} • Street Cred: **{new_cred}**")

    @group.command(name="top", description="Top Street Cred")
    async def top(inter: Interaction):
        storage = inter.client.storage
        rows = storage.top_profiles_by_cred(10)
        if not rows:
            await inter.response.send_message("Personne n’a encore de créd 😶"); return
        lines = [f"**{i+1}.** <@{int(uid)}> — **{cred}**" for i,(uid,cred) in enumerate(rows)]
        embed = discord.Embed(title="🏁 Street Cred — Top 10", description="\n".join(lines), color=discord.Color.dark_gold())
        await inter.response.send_message(embed=embed)

    if guild_obj: tree.add_command(group, guild=guild_obj)
    else:         tree.add_command(group)