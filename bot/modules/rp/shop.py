from __future__ import annotations
import discord
from discord import app_commands, Interaction

from bot.modules.rp.items import ITEMS
from bot.modules.common.money import fmt_eur
from bot.domain import players as d_players
from bot.domain import stats as d_stats
from bot.domain import inventory as d_inventory
from bot.domain import economy as d_economy

shop = app_commands.Group(name="shop", description="Acheter des objets pour booster tes gains.")

# --- Helpers --------------------------------------------------------

def _must_started(user_id: int) -> bool:
    p = d_players.get(user_id)
    return bool(p and p.get("has_started"))

def _unlock_status(user_id: int, item_def: dict) -> tuple[bool, str]:
    """Retourne (débloqué?, message court)."""
    reqs: dict[str, int] = item_def.get("unlock_cmd", {}) or {}
    if not reqs:
        return True, "✅ Débloqué"
    parts, ok_all = [], True
    for stat_key, needed in reqs.items():
        cur = int(d_stats.get(user_id, stat_key, 0))
        if cur < int(needed):
            ok_all = False
        label = stat_key.replace("_count", "")
        parts.append(f"{label} {cur}/{int(needed)}")
    return (True, "✅ Débloqué") if ok_all else (False, "🔒 " + " • ".join(parts))

def _max_qty_for_item(it: dict) -> int:
    if "max_qty" in it:
        return max(1, int(it["max_qty"]))
    if it.get("one_time"):
        return 1
    bonus = it.get("bonus") or {}
    boost_keys = (
        "mendier_flat_min", "mendier_flat_max", "mendier_mult",
        "fouiller_flat_min", "fouiller_flat_max", "fouiller_mult",
    )
    if any(k in bonus for k in boost_keys):
        return 1
    return 99

def _fmt_eur_plain(cents: int) -> str:
    return fmt_eur(cents).split()[0]

# --- Commands -------------------------------------------------------

@shop.command(name="list", description="Voir la liste des objets disponibles")
async def shop_list(inter: Interaction):
    uid = inter.user.id

    if not _must_started(uid):
        await inter.response.send_message("🚀 Utilise **/start** avant.", ephemeral=True)
        return

    money_cents = d_economy.balance(uid)
    inv = d_inventory.get(uid)

    lines: list[str] = []
    for iid, it in ITEMS.items():
        price_cents = int(it["price"])
        name = it["name"]
        desc = it.get("desc", "")

        unlocked, status = _unlock_status(uid, it)
        owned = int(inv.get(iid, 0))
        cap = _max_qty_for_item(it)

        if owned >= cap:
            status = "✅ Possédé"
            buy_hint = "—"
        else:
            buy_hint = f"`/shop buy item:{iid}`" if unlocked else ""

        lines.append(
            f"**{name}** — **{fmt_eur(price_cents)}**  {status}\n"
            f"{desc}\n{buy_hint}"
        )

    embed = discord.Embed(
        title="🛒 Shop — LaRue.exe",
        description="\n\n".join(lines) if lines else "Rien pour l’instant.",
        color=discord.Color.green(),
    )
    embed.set_footer(text=f"Ton solde: {_fmt_eur_plain(money_cents)}")
    await inter.response.send_message(embed=embed, ephemeral=False)

@shop.command(name="buy", description="Acheter un objet du shop")
@app_commands.describe(item="ID de l'objet (ex: cup, sign, dog)")
async def shop_buy(inter: Interaction, item: str):
    uid = inter.user.id

    if not _must_started(uid):
        await inter.response.send_message("🚀 Utilise **/start** avant.", ephemeral=True)
        return

    iid = item.lower().strip()
    it = ITEMS.get(iid)
    if not it:
        await inter.response.send_message("❌ Objet inconnu. Essaye `/shop list`.", ephemeral=True)
        return

    # Cap/possession
    cap = _max_qty_for_item(it)
    owned_before = int(d_inventory.get(uid).get(iid, 0))
    if owned_before >= cap:
        await inter.response.send_message("🛑 Tu possèdes déjà cet objet (limite atteinte).", ephemeral=True)
        return

    # Déblocage
    unlocked, status = _unlock_status(uid, it)
    if not unlocked:
        await inter.response.send_message(
            f"{status}\nTu n’as pas encore déverrouillé **{it['name']}**.",
            ephemeral=True
        )
        return

    # Paiement — idempotent via ledger
    price_cents = int(it["price"])
    before = d_economy.balance(uid)
    if before < price_cents:
        need = price_cents - before
        await inter.response.send_message(
            f"💸 Il te manque **{fmt_eur(need)}**. Prix: **{fmt_eur(price_cents)}**",
            ephemeral=True
        )
        return

    idem_key = f"shop:{inter.id}:{iid}"
    after = d_economy.debit_once(uid, price_cents, reason=f"shop:{iid}", idem_key=idem_key)
    applied = (after == before - price_cents)  # idempotent-safe (si rejoué, ça ne redébite pas)

    # Ajout inventaire: seulement si le débit vient d’être appliqué
    if applied:
        d_inventory.add_item(uid, iid, 1)

    new_balance = d_economy.balance(uid)
    await inter.response.send_message(
        f"✅ Achat de **{it['name']}** pour **{fmt_eur(price_cents)}**. "
        f"Nouveau solde: **{fmt_eur(new_balance)}**",
        ephemeral=False
    )

@shop.command(name="inventory", description="Voir ton inventaire")
async def shop_inventory(inter: Interaction):
    uid = inter.user.id

    if not _must_started(uid):
        await inter.response.send_message("🚀 Utilise **/start** avant.", ephemeral=True)
        return

    inv = d_inventory.get(uid)
    if not inv:
        await inter.response.send_message("🧺 Inventaire vide. Va voir `/shop list`.", ephemeral=True)
        return

    lines: list[str] = []
    for iid, qty in inv.items():
        it = ITEMS.get(iid, {"name": iid})
        cap = _max_qty_for_item(it)
        cap_txt = f" (max {cap})" if cap < 99 else ""
        lines.append(f"**{it['name']}** × {qty}{cap_txt}")

    embed = discord.Embed(
        title="🧺 Ton inventaire",
        description="\n".join(lines),
        color=discord.Color.blurple()
    )
    await inter.response.send_message(embed=embed, ephemeral=False)

def register(tree: app_commands.CommandTree, guild_obj: discord.Object | None):
    if guild_obj:
        tree.add_command(shop, guild=guild_obj)
    else:
        tree.add_command(shop)
