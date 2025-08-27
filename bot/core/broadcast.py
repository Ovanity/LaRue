# bot/core/broadcast.py
from __future__ import annotations
import os, logging
import discord

from bot.persistence import broadcast as repo_broadcast

log = logging.getLogger(__name__)

def _env_flag(name: str, default: bool=False) -> bool:
    v = os.getenv(name)
    return default if v is None else v.lower() in ("1", "true", "yes", "on")

class BroadcastService:
    """
    Transport unique: poste dans OFFICIAL_FEED_CHANNEL_ID si tout est OK.
    Indépendant du scope global/guild des slash (on vise un channel_id précis).
    """
    enabled: bool = False
    guild_id: int | None = None
    channel_id: int | None = None
    channel: discord.abc.MessageableChannel | None = None

    @classmethod
    async def init(cls, client: discord.Client) -> None:
        cls.guild_id   = int(os.getenv("OFFICIAL_GUILD_ID", "0") or 0)
        cls.channel_id = int(os.getenv("OFFICIAL_FEED_CHANNEL_ID", "0") or 0)

        if not _env_flag("BROADCAST_ENABLED", False):
            log.info("Broadcast disabled by env; nothing will be posted.")
            cls.enabled = False
            return

        if not cls.guild_id or not cls.channel_id:
            log.warning("Broadcast misconfigured: missing OFFICIAL_GUILD_ID or OFFICIAL_FEED_CHANNEL_ID.")
            cls.enabled = False
            return

        ch = client.get_channel(cls.channel_id)
        if ch is None:
            try:
                ch = await client.fetch_channel(cls.channel_id)
            except Exception as e:
                log.warning("Broadcast channel fetch failed: %s", e)
                cls.enabled = False
                return

        if getattr(ch, "guild", None) is None or ch.guild.id != cls.guild_id:
            log.warning("Broadcast channel does not belong to OFFICIAL_GUILD_ID.")
            cls.enabled = False
            return

        me = ch.guild.me
        if me is None:
            me = ch.guild.get_member(client.user.id)  # type: ignore
        if me is None:
            log.warning("Broadcast cannot resolve bot member in guild.")
            cls.enabled = False
            return

        perms = ch.permissions_for(me)  # type: ignore
        if not perms.send_messages or not perms.embed_links:
            log.warning("Broadcast missing permissions in channel (send_messages, embed_links).")
            cls.enabled = False
            return

        cls.channel = ch
        cls.enabled = True
        log.info("Broadcast ready: guild=%s channel=%s", cls.guild_id, cls.channel_id)

    @staticmethod
    def _jump_url(gid: int, cid: int, mid: int) -> str:
        return f"https://discord.com/channels/{gid}/{cid}/{mid}"

    @classmethod
    async def post_embed(cls, event_key: str, embed: discord.Embed) -> str | None:
        """Idempotent: ne reposte pas si déjà loggé. Renvoie jump_url si succès."""
        if not cls.enabled or cls.channel is None:
            return None
        if repo_broadcast.was_broadcasted(event_key):
            rec = repo_broadcast.get_broadcast(event_key)
            return rec["jump_url"] if rec else None

        try:
            msg = await cls.channel.send(embed=embed)  # type: ignore
            jump = cls._jump_url(cls.guild_id, cls.channel_id, msg.id)  # type: ignore
            repo_broadcast.record_broadcast(event_key, str(cls.guild_id), str(cls.channel_id), str(msg.id), jump)
            return jump
        except Exception:
            log.exception("Broadcast post failed for key=%s", event_key)
            return None
