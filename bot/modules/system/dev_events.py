from __future__ import annotations
import time, json
from discord import app_commands, Interaction

from bot.persistence import events as repo_events

@app_commands.command(name="dev_seed_event", description="[DEV] Planifie un event dans la table events.")
@app_commands.describe(
    kind="Type d'event (ex: boost_window, first_claims, patch)",
    delay_sec="Dans combien de secondes il doit démarrer (défaut: 5)",
    duration_sec="Durée en secondes (0 = pas de fin)",
    title="Titre affiché (facultatif)",
    payload_json='Payload JSON (ex: {"desc":"Hello","mult":1.2})'
)
async def dev_seed_event(
    inter: Interaction,
    kind: str,
    delay_sec: int = 5,
    duration_sec: int = 0,
    title: str | None = None,
    payload_json: str | None = None,
):
    # Auth minimal : limite aux admins du serveur de test (facultatif)
    if not inter.user.guild_permissions.administrator:
        await inter.response.send_message("Réservé aux admins.", ephemeral=True)
        return

    now = int(time.time())
    starts_at = now + max(0, int(delay_sec))
    ends_at = starts_at + int(duration_sec) if duration_sec > 0 else 0

    # Clé métier (idempotence logique côté events)
    event_id = f"{kind}:{starts_at}"

    try:
        payload = json.loads(payload_json) if payload_json else {}
    except Exception:
        await inter.response.send_message("Payload JSON invalide.", ephemeral=True)
        return

    ev = repo_events.upsert_event(
        event_id=event_id,
        kind=kind,
        title=title or "",
        starts_at=starts_at,
        ends_at=ends_at,
        payload=payload,
        status="scheduled",
    )
    await inter.response.send_message(
        f"✅ Event seedé.\nID: `{ev['id']}`\nStart: <t:{ev['starts_at']}:R>\nKind: `{ev['kind']}`",
        ephemeral=True,
    )

def register(tree, guild_obj, client=None):
    # Dev-only : on enregistre la commande uniquement sur la/les guild(s) de test
    if guild_obj:
        tree.add_command(dev_seed_event, guild=guild_obj)