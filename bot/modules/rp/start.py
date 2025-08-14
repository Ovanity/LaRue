from __future__ import annotations
import discord
from discord import app_commands, Interaction, Embed

# On réutilise les actions ET les constantes (cooldowns/caps) depuis economy
from bot.modules.rp.economy import (
    mendier_action, fouiller_action, stats_action,
    MENDIER_COOLDOWN_S, MENDIER_DAILY_CAP,
    FOUILLER_COOLDOWN_S, FOUILLER_DAILY_CAP,
)

# Palette de couleurs (choisie selon l'utilisateur)
PALETTE = [
    discord.Color.blurple(),
    discord.Color.dark_teal(),
    discord.Color.dark_gold(),
    discord.Color.purple(),
    discord.Color.dark_orange(),
]

WELCOME_INTRO = (
    "🖥️ **Mode Survie Activé**\n"
    "Wesh {mention}, t’es arrivé ici **sans thunes**, sans matos, et avec un vieux carton.\n"
    "T’es direct dans **la sauce**."
)
WELCOME_RULES = (
    "📜 **Règles du terrain**\n"
    "💰 Tu veux graille ? → *Tu mendies*\n"
    "🗑️ Tu veux du matos ? → *Tu fouilles*\n"
    "🏃 Tu veux survivre ? → *Tu bouges vite*"
)
WELCOME_HINTS = (
    "▶️ Utilise les **boutons** ci‑dessous pour agir tout de suite\n"
    "ou tape : `/hesshelp` • pour avoir plus d'informations.\n"
)

# ─────────────────────────────
# Helpers cooldown/quotas
# ─────────────────────────────
def _fmt_wait(secs: int) -> str:
    s = int(max(0, secs))
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    if h: return f"{h}h{m:02d}m{s:02d}s"
    if m: return f"{m}m{s:02d}s"
    return f"{s}s"

def _check_limit(storage, user_id: int, action: str, cd: int, cap: int) -> tuple[bool, str | None]:
    """Utilise storage.check_and_touch_action si dispo; sinon laisse passer."""
    if not hasattr(storage, "check_and_touch_action"):
        return True, None
    ok, wait, remaining = storage.check_and_touch_action(user_id, action, cd, cap)
    if ok:
        return True, None
    if remaining == 0:
        return False, "⛔ T’as tout claqué aujourd’hui. Reviens demain."
    return False, f"⏳ Reviens dans **{_fmt_wait(wait)}** (reste **{remaining}** fois aujourd’hui)."


# ─────────────────────────────
# Vue de démarrage
# ─────────────────────────────
class StartView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=120)  # 120s d'activité
        self.owner_id = owner_id
        self.message: discord.Message | None = None  # rempli après envoi

    async def _guard(self, inter: Interaction) -> bool:
        if inter.user.id != self.owner_id:
            await inter.response.send_message(
                "🛑 Ce menu n'est pas à toi mon reuf, tu joues à quoi ?",
                ephemeral=True
            )
            return False
        return True

    async def on_timeout(self) -> None:
        """Remplace l'embed par un message d'expiration et supprime les boutons."""
        if not self.message:
            return
        try:
            expired_embed = discord.Embed(
                description="⏳ Ce menu est expiré, il fallait se bouger mon reuf.",
                color=discord.Color.dark_grey()
            )
            await self.message.edit(embed=expired_embed, view=None)
            self.stop()
        except discord.NotFound:
            pass

    @discord.ui.button(label="🥖 Mendier", style=discord.ButtonStyle.primary, custom_id="start_mendier")
    async def btn_mendier(self, inter: Interaction, _: discord.ui.Button):
        if not await self._guard(inter): return
        storage = inter.client.storage
        p = storage.get_player(inter.user.id)
        if not p.get("has_started"):
            await inter.response.send_message("🛑 Lance /start d’abord.", ephemeral=True); return

        ok, msg = _check_limit(storage, inter.user.id, "mendier", MENDIER_COOLDOWN_S, MENDIER_DAILY_CAP)
        if not ok:
            await inter.response.send_message(msg, ephemeral=True); return

        res = mendier_action(storage, inter.user.id)
        await inter.response.send_message(res["msg"])

    @discord.ui.button(label="🗑️ Fouiller", style=discord.ButtonStyle.success, custom_id="start_fouiller")
    async def btn_fouiller(self, inter: Interaction, _: discord.ui.Button):
        if not await self._guard(inter): return
        storage = inter.client.storage
        p = storage.get_player(inter.user.id)
        if not p.get("has_started"):
            await inter.response.send_message("🛑 Lance /start d’abord.", ephemeral=True); return

        ok, msg = _check_limit(storage, inter.user.id, "fouiller", FOUILLER_COOLDOWN_S, FOUILLER_DAILY_CAP)
        if not ok:
            await inter.response.send_message(msg, ephemeral=True); return

        res = fouiller_action(storage, inter.user.id)
        await inter.response.send_message(res["msg"])

    @discord.ui.button(label="📊 Stats", style=discord.ButtonStyle.secondary, custom_id="start_stats")
    async def btn_stats(self, inter: Interaction, _: discord.ui.Button):
        if not await self._guard(inter): return
        storage = inter.client.storage
        p = storage.get_player(inter.user.id)
        if not p or not p.get("has_started"):
            await inter.response.send_message("🛑 Lance /start d’abord.", ephemeral=True); return
        await inter.response.send_message(stats_action(storage, inter.user.id))


# ─────────────────────────────
# Commande /start
# ─────────────────────────────
def register(tree: app_commands.CommandTree, guild_obj: discord.Object | None, client: discord.Client):
    @tree.command(name="start", description="Commence ton aventure dans LaRue.exe")
    @app_commands.guilds(guild_obj) if guild_obj else (lambda f: f)
    async def start(inter: Interaction):
        storage = client.storage
        p = storage.get_player(inter.user.id)

        if p and p.get("has_started"):
            await inter.response.send_message(
                "🛑 Mon reuf, t’as déjà lancé LaRue.exe. Pas de deuxième spawn.",
                ephemeral=True
            )
            return

        storage.update_player(inter.user.id, has_started=True, money=0)

        # Couleur choisie selon l'utilisateur (stable mais variée)
        color = PALETTE[inter.user.id % len(PALETTE)]
        SP = "\u2800"  # espace invisible qui prend une ligne

        embed = Embed(title="🌆 LaRue.exe", color=color)
        embed.add_field(
            name="Introduction",
            value=f"{SP}\n" + WELCOME_INTRO.format(mention=inter.user.mention) + "\n\n\u200b",
            inline=False
        )
        embed.add_field(
            name="Code de LaRue.exe",
            value=f"{SP}\n" + WELCOME_RULES + "\n\n\u200b",
            inline=False
        )
        embed.add_field(
            name="Tips",
            value=f"{SP}\n" + WELCOME_HINTS + "\n",
            inline=False
        )
        embed.set_footer(text="Choisis une action pour commencer • LaRue.exe")

        # Envoi + enregistrement du message pour le timeout
        view = StartView(inter.user.id)
        await inter.response.send_message(embed=embed, view=view, ephemeral=False)
        view.message = await inter.original_response()