from __future__ import annotations
import discord
from discord import app_commands, Interaction
from bot.modules.rp.items import ITEMS

shop = app_commands.Group(name="shop", description="Acheter des objets pour booster tes gains.")

@shop.command(name="list", description="Voir la liste des objets disponibles")
async def shop_list(inter: Interaction):
    storage = inter.client.storage
    money = storage.get_money(inter.user.id)

    lines = []
    for iid, it in ITEMS.items():
        lines.append(f"**{it['name']}** — **{it['price']}€**\n{it['desc']}\n`/shop buy item:{iid}`")
    desc = "\n\n".join(lines)

    embed = discord.Embed(title="🛒 Shop — LaRue.exe", description=desc, color=discord.Color.green())
    embed.set_footer(text=f"Ton solde: {money}€")
    await inter.response.send_message(embed=embed, ephemeral=False)

@shop.command(name="buy", description="Acheter un objet du shop")
@app_commands.describe(item="ID de l'objet (ex: cup, sign, dog)")
async def shop_buy(inter: Interaction, item: str):
    storage = inter.client.storage
    item = item.lower().strip()
    it = ITEMS.get(item)
    if not it:
        await inter.response.send_message("❌ Objet inconnu. Essaye `/shop list`.", ephemeral=True); return

    # Déblocage simple: patrimoine minimal (unlock_at)
    have_money = storage.get_money(inter.user.id)
    if have_money < it["unlock_at"]:
        await inter.response.send_message(
            f"🔒 Pas encore prêt. Il te faut au moins **{it['unlock_at']}€** de patrimoine pour *{it['name']}*.",
            ephemeral=True
        ); return

    price = int(it["price"])
    if not storage.try_spend(inter.user.id, price):
        await inter.response.send_message(f"💸 Il te manque des sous. Prix: **{price}€**", ephemeral=True); return

    storage.add_item(inter.user.id, item, 1)
    await inter.response.send_message(f"✅ Achat de **{it['name']}** pour **{price}€**. Bien vu !", ephemeral=False)

@shop.command(name="inventory", description="Voir ton inventaire")
async def shop_inventory(inter: Interaction):
    storage = inter.client.storage
    inv = storage.get_inventory(inter.user.id)
    if not inv:
        await inter.response.send_message("🧺 Inventaire vide. Achète quelque chose dans `/shop list`.", ephemeral=True)
        return

    lines = []
    for iid, qty in inv.items():
        it = ITEMS.get(iid, {"name": iid})
        lines.append(f"**{it['name']}** × {qty}")
    embed = discord.Embed(title="🧺 Ton inventaire", description="\n".join(lines), color=discord.Color.blurple())
    await inter.response.send_message(embed=embed, ephemeral=False)

def register(tree: app_commands.CommandTree, guild_obj: discord.Object | None):
    if guild_obj: tree.add_command(shop, guild=guild_obj)
    else:         tree.add_command(shop)