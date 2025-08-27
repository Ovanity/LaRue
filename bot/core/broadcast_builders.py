from __future__ import annotations
import discord
from typing import Dict

def build_generic(title: str, desc: str = "") -> discord.Embed:
    e = discord.Embed(title=title or "LaRue.exe", description=desc or "", color=discord.Color.blurple())
    e.set_footer(text="LaRue.exe — Le Fil")
    return e

def build_from_event(ev: Dict) -> discord.Embed:
    """
    ev: dict depuis repo_events (id, kind, title, payload, starts_at, ends_at, ...)
    On reste simple: title + petits champs selon kind (libre).
    """
    title = ev.get("title") or ev.get("kind") or "LaRue.exe"
    payload = ev.get("payload") or {}
    desc = payload.get("desc") or payload.get("message") or ""
    e = build_generic(title, desc)

    starts = ev.get("starts_at", 0)
    ends   = ev.get("ends_at", 0)
    if starts:
        e.add_field(name="Début", value=f"<t:{int(starts)}:f>")
    if ends:
        e.add_field(name="Fin", value=f"<t:{int(ends)}:f>")
    return e
