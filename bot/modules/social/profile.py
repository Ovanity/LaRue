from __future__ import annotations
from typing import Optional
import discord
from discord import app_commands, Interaction
from bot.modules.common.money import fmt_eur

def _color(hexstr: str) -> discord.Color:
    try:
        return discord.Color(int(hexstr.strip("#"), 16))
    except Exception:
        return discord.Color.dark_grey()

def _display_name(inter: Interaction, user: discord.abc.User) -> str:
    # Pseudo serveur si possible, sinon global_name / name
    if inter.guild:
        m = inter.guild.get_member(user.id)
        if m and m.display_name:
            return m.display_name
    return getattr(user, "global_name", None) or user.name

def _avatar_url(u: discord.abc.User | discord.Member, size: int = 512) -> str:
    # Asset → URL (taille large)
    try:
        return u.display_avatar.with_size(size).url
    except Exception:
        try:
            return u.display_avatar.url
        except Exception:
            return ""

def _embed_profile(inter: Interaction, storage, target: discord.User | discord.Member) -> discord.Embed:
        prof   = storage.get_profile(target.id)
        player = storage.get_player(target.id)

        name  = _display_name(inter, target)
        money = fmt_eur(player["money"])
        color = _color(prof.get("color_hex", "FFD166"))
        bio   = prof.get("bio") or "Aucune bio."
        cred  = str(int(prof.get("cred", 0)))
        custom_title = prof.get("title") or None

        e = discord.Embed(
            title=f"🪪 {name}",
            description=bio,
            color=color
        )

        # Avatar en GRAND en haut
        url = _avatar_url(target, size=512)
        if url:
            e.set_image(url=url)

        # Infos principales
        e.add_field(name="💰 Biftons", value=money, inline=True)
        e.add_field(name="🧿 Street Cred", value=cred, inline=True)

        # (optionnel) titre perso
        if custom_title:
            e.add_field(name="🏷️ Titre", value=str(custom_title), inline=False)

        # Footer discret
        tag = f"{getattr(target, 'name', 'user')}#{getattr(target, 'discriminator', '0')}"
        e.set_footer(text=f"Profil • {tag} • ID {target.id}")
        return e

def register(tree: app_commands.CommandTree, guild_obj: Optional[discord.Object], client: discord.Client | None = None):
    group = app_commands.Group(name="profil", description="Profil social LaRue.exe")

    @group.command(name="voir", description="Afficher un profil (par défaut: toi)")
    @app_commands.describe(user="(optionnel) quelqu’un d’autre du serveur")
    async def voir(inter: Interaction, user: Optional[discord.User] = None):
        storage = inter.client.storage

        if not inter.guild:
            await inter.response.send_message("❌ Commande uniquement sur le serveur.", ephemeral=True)
            return

        target = user or inter.user

        # pas de profil pour les bots
        if getattr(target, "bot", False):
            await inter.response.send_message("🤖 Les bots n’ont pas de profil ici.", ephemeral=True)
            return

        # doit être membre du serveur
        member = inter.guild.get_member(target.id)
        if not member:
            await inter.response.send_message("🚧 Cette personne n’est pas sur ce serveur.", ephemeral=True)
            return

        # doit avoir /start
        tp = storage.get_player(target.id)
        if not tp or not tp.get("has_started"):
            if target.id == inter.user.id:
                await inter.response.send_message("🚀 Lance **/start** pour créer ton profil.", ephemeral=True)
            else:
                await inter.response.send_message("ℹ️ Cette personne n’a pas encore commencé (**/start**).", ephemeral=True)
            return

        await inter.response.send_message(embed=_embed_profile(inter, storage, target))

    @group.command(name="set_bio", description="Définir ta bio (160 max)")
    async def set_bio(inter: Interaction, bio: str):
        storage = inter.client.storage
        p = storage.get_player(inter.user.id)
        if not p or not p.get("has_started"):
            await inter.response.send_message("🚀 Lance **/start** avant de modifier ton profil.", ephemeral=True)
            return
        if len(bio) > 160:
            await inter.response.send_message("❌ 160 caractères max.", ephemeral=True)
            return
        storage.upsert_profile(inter.user.id, bio=bio.strip())
        await inter.response.send_message("✅ Bio mise à jour.", ephemeral=True)

    @group.command(name="respect", description="Donner +1 Street Cred (1/jour par personne)")
    async def respect(inter: Interaction, user: discord.User):
        if not inter.guild:
            await inter.response.send_message("❌ Commande uniquement sur le serveur.", ephemeral=True)
            return

        if user.id == inter.user.id:
            await inter.response.send_message("😅 Tu peux pas te respecter toi-même.", ephemeral=True)
            return
        if getattr(user, "bot", False):
            await inter.response.send_message("🤖 Pas de respect pour les bots (ils en ont déjà trop).", ephemeral=True)
            return

        member = inter.guild.get_member(user.id)
        if not member:
            await inter.response.send_message("🚧 Cette personne n’est pas sur ce serveur.", ephemeral=True)
            return

        storage = inter.client.storage
        tp = storage.get_player(user.id)
        if not tp or not tp.get("has_started"):
            await inter.response.send_message("ℹ️ Cette personne n’a pas encore commencé (**/start**).", ephemeral=True)
            return

        ok, why = storage.can_give_respect(inter.user.id, user.id)
        if not ok:
            await inter.response.send_message(why or "⏳ Demain.", ephemeral=True)
            return

        new_cred = storage.give_respect(inter.user.id, user.id)
        await inter.response.send_message(f"🤝 Respect donné à {user.mention} • Street Cred: **{new_cred}**")

    @group.command(name="top", description="Top Street Cred (serveur)")
    async def top(inter: Interaction):
        if not inter.guild:
            await inter.response.send_message("❌ Commande uniquement sur le serveur.", ephemeral=True)
            return

        storage = inter.client.storage
        rows = storage.top_profiles_by_cred(30)  # on tire large puis on filtre
        # filtre aux membres du serveur ayant /start
        filtered = []
        for uid, cred in rows:
            m = inter.guild.get_member(int(uid))
            if not m:
                continue
            p = storage.get_player(int(uid))
            if p and p.get("has_started"):
                filtered.append((uid, cred))
            if len(filtered) >= 10:
                break

        if not filtered:
            await inter.response.send_message("Personne n’a encore de créd 😶")
            return

        lines = [f"**{i+1}.** <@{int(uid)}> — **{cred}**" for i, (uid, cred) in enumerate(filtered)]
        embed = discord.Embed(
            title="🏁 Street Cred — Top 10 (serveur)",
            description="\n".join(lines),
            color=discord.Color.dark_gold()
        )
        await inter.response.send_message(embed=embed)

    if guild_obj:
        tree.add_command(group, guild=guild_obj)
    else:
        tree.add_command(group)