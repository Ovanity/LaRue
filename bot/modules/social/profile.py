# bot/modules/social/profile.py — refactor sans storage (domain only)
from __future__ import annotations
from typing import Optional
import discord
from discord import app_commands, Interaction

from bot.modules.common.money import fmt_eur
from bot.domain import economy as d_economy
from bot.domain import players as d_players
from bot.domain import profiles as d_profiles
from bot.domain import respect as d_respect

MAX_BIO_LEN = 160

# ─────────────────────────────
# Utils
# ─────────────────────────────
def _color(hexstr: str) -> discord.Color:
    try:
        return discord.Color(int(hexstr.strip().lstrip("#"), 16))
    except Exception:
        return discord.Color.dark_grey()

def _display_name(inter: Interaction, user: discord.abc.User) -> str:
    if inter.guild:
        m = inter.guild.get_member(user.id)
        if m and m.display_name:
            return m.display_name
    return getattr(user, "global_name", None) or user.name

def _avatar_url(u: discord.abc.User | discord.Member, size: int = 256) -> str:
    try:
        return u.display_avatar.with_size(size).url
    except Exception:
        try:
            return u.display_avatar.url
        except Exception:
            return ""

async def _get_member(inter: Interaction, user: discord.abc.User) -> Optional[discord.Member]:
    if not inter.guild:
        return None
    m = inter.guild.get_member(user.id)
    if m:
        return m
    try:
        return await inter.guild.fetch_member(user.id)
    except (discord.NotFound, discord.HTTPException, discord.Forbidden):
        return None

def _mask_id(user_id: int) -> str:
    s = str(user_id)
    return f"…{s[-4:]}" if len(s) >= 4 else "…"

async def _require_guild(inter: Interaction) -> bool:
    if not inter.guild:
        await inter.response.send_message("❌ Commande uniquement sur le serveur.", ephemeral=True)
        return False
    return True

def _has_started(user_id: int) -> bool:
    p = d_players.get(user_id)
    return bool(p and p.get("has_started"))

# ─────────────────────────────
# Embed
# ─────────────────────────────
def _embed_profile(inter: Interaction, target: discord.User | discord.Member) -> discord.Embed:
    prof = d_profiles.get(target.id)
    name = _display_name(inter, target)
    balance = d_economy.balance(target.id)  # source de vérité: ledger
    money_str = fmt_eur(balance)

    color = _color(prof.get("color_hex", "FFD166"))
    bio = prof.get("bio") or "Aucune bio."
    cred = str(int(prof.get("cred", 0)))
    custom_title = prof.get("title") or None

    e = discord.Embed(title=f"🪪 {name}", color=color)

    url = _avatar_url(target, size=256)
    if url:
        e.set_thumbnail(url=url)

    e.add_field(name="💰 Capital", value=money_str, inline=True)
    e.add_field(name="🧿 Street Cred", value=cred, inline=True)

    if custom_title:
        e.add_field(name="🏷️ Titre", value=str(custom_title), inline=False)

    e.add_field(name="📝 Bio", value=bio, inline=False)

    tag = getattr(target, "name", "user")
    e.set_footer(text=f"Profil • {tag} • UID {_mask_id(target.id)}")
    return e

# ─────────────────────────────
# Slash commands
# ─────────────────────────────
def register(tree: app_commands.CommandTree, guild_obj: Optional[discord.Object], client: discord.Client | None = None):
    group = app_commands.Group(name="profil", description="Profil social LaRue.exe")

    @group.command(name="voir", description="Afficher un profil (par défaut: toi)")
    @app_commands.describe(user="(optionnel) quelqu’un d’autre du serveur")
    async def voir(inter: Interaction, user: Optional[discord.User] = None):
        if not await _require_guild(inter):
            return

        target = user or inter.user

        if getattr(target, "bot", False):
            await inter.response.send_message("🤖 Les bots n’ont pas de profil ici.", ephemeral=True)
            return

        member = target if isinstance(target, discord.Member) else await _get_member(inter, target)
        if not member:
            await inter.response.send_message("🚧 Cette personne n’est pas sur ce serveur.", ephemeral=True)
            return

        if not _has_started(target.id):
            if target.id == inter.user.id:
                await inter.response.send_message("🚀 Lance **/start** pour créer ton profil.", ephemeral=True)
            else:
                await inter.response.send_message("ℹ️ Cette personne n’a pas encore commencé (**/start**).", ephemeral=True)
            return

        await inter.response.send_message(embed=_embed_profile(inter, member))

    @group.command(name="set_bio", description=f"Définir ta bio ({MAX_BIO_LEN} max)")
    @app_commands.describe(bio="Texte court affiché sur ton profil")
    async def set_bio(inter: Interaction, bio: str):
        if not _has_started(inter.user.id):
            await inter.response.send_message("🚀 Lance **/start** avant de modifier ton profil.", ephemeral=True)
            return
        if len(bio) > MAX_BIO_LEN:
            await inter.response.send_message(f"❌ {MAX_BIO_LEN} caractères max.", ephemeral=True)
            return

        d_profiles.upsert(inter.user.id, bio=bio.strip())
        await inter.response.send_message("✅ Bio mise à jour.", ephemeral=True)

    @group.command(name="respect", description="Donner +1 Street Cred (1/jour par personne)")
    @app_commands.describe(user="La personne à qui tu donnes du respect")
    async def respect(inter: Interaction, user: discord.User):
        if not await _require_guild(inter):
            return
        if user.id == inter.user.id:
            await inter.response.send_message("😅 Tu peux pas te respecter toi-même.", ephemeral=True)
            return
        if getattr(user, "bot", False):
            await inter.response.send_message("🤖 Pas de respect pour les bots (ils en ont déjà trop).", ephemeral=True)
            return

        member = await _get_member(inter, user)
        if not member:
            await inter.response.send_message("🚧 Cette personne n’est pas sur ce serveur.", ephemeral=True)
            return

        if not _has_started(user.id):
            await inter.response.send_message("ℹ️ Cette personne n’a pas encore commencé (**/start**).", ephemeral=True)
            return

        ok, why = d_respect.can_give(inter.user.id, user.id)
        if not ok:
            await inter.response.send_message(why or "⏳ Demain.", ephemeral=True)
            return

        new_cred = d_respect.give(inter.user.id, user.id)
        await inter.response.send_message(f"🤝 Respect donné à {user.mention} • Street Cred: **{new_cred}**")

    @group.command(name="top", description="Top Street Cred (serveur)")
    async def top(inter: Interaction):
        if not await _require_guild(inter):
            return

        rows = d_profiles.top_by_cred(50)  # [(user_id:str|int, cred:int)]
        filtered: list[tuple[int, int]] = []

        for uid, cred in rows:
            try:
                uid_i = int(uid)
                cred_i = int(cred)
            except Exception:
                continue

            # 1) doit être membre du serveur
            member = inter.guild.get_member(uid_i) or await _get_member(inter, discord.Object(id=uid_i))  # type: ignore
            if not member:
                continue
            # 2) doit avoir /start
            if not _has_started(uid_i):
                continue

            filtered.append((uid_i, cred_i))
            if len(filtered) >= 10:
                break

        if not filtered:
            await inter.response.send_message("Personne n’a encore de créd 😶", ephemeral=True)
            return

        lines = [f"**{i + 1}.** <@{uid}> — **{cred}**" for i, (uid, cred) in enumerate(filtered)]
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
