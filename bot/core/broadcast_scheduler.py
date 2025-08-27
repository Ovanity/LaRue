from __future__ import annotations
import asyncio, random, time, logging
from bot.core.broadcast import BroadcastService
from bot.core import broadcast_builders as builders
from bot.persistence import events as repo_events
from bot.persistence import broadcast as repo_broadcast

log = logging.getLogger(__name__)

class BroadcastTicker:
    _task: asyncio.Task | None = None

    @classmethod
    def start(cls, client) -> None:
        if cls._task and not cls._task.done():
            return
        cls._task = asyncio.create_task(cls._run())

    @classmethod
    async def _run(cls):
        # Jitter initial pour ne pas tirer pile au boot
        await asyncio.sleep(random.randint(5, 20))
        while True:
            try:
                if not BroadcastService.enabled:
                    await asyncio.sleep(30); continue

                now = int(time.time())
                for ev in repo_events.list_due(now, limit=5):
                    key = ev["id"]
                    if repo_broadcast.was_broadcasted(key):
                        # Si on a déjà un log mais l'event est encore 'scheduled', on met à jour en 'published' par sécurité
                        # (utile si crash après envoi)
                        continue
                    embed = builders.build_from_event(ev)
                    jump = await BroadcastService.post_embed(key, embed)
                    if jump:
                        repo_events.set_published(ev["id"], jump)

                # cadence ~ 60s ± jitter
                await asyncio.sleep(60 + random.randint(-10, 10))
            except Exception:
                log.exception("Broadcast ticker error")
                await asyncio.sleep(10)
