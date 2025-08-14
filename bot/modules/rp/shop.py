from __future__ import annotations
import discord
from discord import app_commands, Interaction

from bot.modules.rp.items import ITEMS
from bot.modules.common.money import fmt_eur  # formate les centimes en €

shop = app_commands.Group(name="shop", description="Acheter des objets pour booster tes gains.")

def _must_started(storage, user_id: int) -> bool:
    p = storage.get_player(user_id)
    return bool(p and p.get("has_started"))

def _unlock_status(storage, user_id: int, item_def: dict) -> tuple[bool, str]:
    """
    Retourne (is_unlocked, details).
    item_def peut contenir:
      - "unlock_cmd": {"mendier_count": 10, "fouiller_count": 1, ...}
    S'il n'y a pas de conditions, on considère l'item débloqué.
    """
    reqs: dict[str, int] = item_def.get("unlock_cmd", {}) or {}
    if not reqs:
        return True, "✅ Débloqué"

    parts = []
    ok_all = True
    for stat_key, needed in reqs.items():
        cur = 0
        if hasattr(storage, "get_stat"):
            cur = int(storage.get_stat(user_id, stat_key, 0))
        if cur < int(needed):
            ok_all = False
        # rendu joli: "mendier 7/10"
        label = stat_key.replace("_count", "")
        parts.append(f"{label} {cur}/{int(needed)}")

    if ok_all:
        return True, "✅ Débloqué"
    return False, "🔒 " + " • ".join(parts)

@shop.command(name="list", description="Voir la liste des objets disponibles")
async def shop_list(inter: Interaction):
    storage = inter.client.storage
    uid = inter.user.id

    if not _must_started(storage, uid):
        await inter.response.send_message("🚀 Utilise **/start** avant.", ephemeral=True)
        return

    money_cents = storage.get_money(uid)

    lines: list[str] = []
    for iid, it in ITEMS.items():
        price_cents = int(it["price"])  # prix en centimes
        name = it["name"]
        desc = it.get("desc", "")

        unlocked, status = _unlock_status(storage, uid, it)

        lines.append(
            f"**{name}** — **{fmt_eur(price_cents)}**  {status}\n"
            f"{desc}\n`/shop buy item:{iid}`"
        )

    embed = discord.Embed(
        title="🛒 Shop — LaRue.exe",
        description="\n\n".join(lines) if lines else "Rien pour l’instant.",
        color=discord.Color.green(),
    )
    embed.set_footer(text=f"Ton solde: {fmt_eur(money_cents)}")
    await inter.response.send_message(embed=embed, ephemeral=False)

@shop.command(name="buy", description="Acheter un objet du shop")
@app_commands.describe(item="ID de l'objet (ex: cup, sign, dog)")
async def shop_buy(inter: Interaction, item: str):
    storage = inter.client.storage
    uid = inter.user.id

    if not _must_started(storage, uid):
        await inter.response.send_message("🚀 Utilise **/start** avant.", ephemeral=True)
        return

    iid = item.lower().strip()
    it = ITEMS.get(iid)
    if not it:
        await inter.response.send_message("❌ Objet inconnu. Essaye `/shop list`.", ephemeral=True)
        return

    # Vérifier le déblocage par compteurs
    unlocked, status = _unlock_status(storage, uid, it)
    if not unlocked:
        await inter.response.send_message(
            f"{status}\nTu n’as pas encore déverrouillé **{it['name']}**.",
            ephemeral=True
        )
        return

    price_cents = int(it["price"])
    have_cents = storage.get_money(uid)

    if not storage.try_spend(uid, price_cents):  # dépense en centimes
        need = max(0, price_cents - have_cents)
        await inter.response.send_message(
            f"💸 Il te manque **{fmt_eur(need)}**. Prix: **{fmt_eur(price_cents)}**",
            ephemeral=True
        )
        return

    storage.add_item(uid, iid, 1)
    new_balance = storage.get_money(uid)
    await inter.response.send_message(
        f"✅ Achat de **{it['name']}** pour **{fmt_eur(price_cents)}**. "
        f"Nouveau solde: **{fmt_eur(new_balance)}**",
        ephemeral=False
    )

@shop.command(name="inventory", description="Voir ton inventaire")
async def shop_inventory(inter: Interaction):
    storage = inter.client.storage
    uid = inter.user.id

    if not _must_started(storage, uid):
        await inter.response.send_message("🚀 Utilise **/start** avant.", ephemeral=True)
        return

    inv = storage.get_inventory(uid)  # {iid: qty}
    if not inv:
        await inter.response.send_message("🧺 Inventaire vide. Va voir `/shop list`.", ephemeral=True)
        return

    lines: list[str] = []
    for iid, qty in inv.items():
        it = ITEMS.get(iid, {"name": iid})
        lines.append(f"**{it['name']}** × {qty}")

    money_cents = storage.get_money(uid)
    embed = discord.Embed(
        title="🧺 Ton inventaire",
        description="\n".join(lines),
        color=discord.Color.blurple()
    )
    embed.set_footer(text=f"Solde: {fmt_eur(money_cents)}")
    await inter.response.send_message(embed=embed, ephemeral=False)

def register(tree: app_commands.CommandTree, guild_obj: discord.Object | None):
    if guild_obj:
        tree.add_command(shop, guild=guild_obj)
    else:
        tree.add_command(shop)