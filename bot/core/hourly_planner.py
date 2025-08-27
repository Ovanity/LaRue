# bot/core/hourly_planner.py
from __future__ import annotations
import asyncio, logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from bot.persistence import events as repo_events

log = logging.getLogger(__name__)

class HourlyPlanner:
    _task: asyncio.Task | None = None
    _tz = ZoneInfo("Europe/Paris")

    @classmethod
    def start(cls):
        if cls._task and not cls._task.done():
            return
        cls._task = asyncio.create_task(cls._run())

    @classmethod
    async def _run(cls):
        # Petit décalage initial pour éviter les courses au boot
        await asyncio.sleep(2)
        while True:
            try:
                now = datetime.now(tz=cls._tz)
                # Prochaine "pile d'heure" locale (DST-safe via zoneinfo)
                next_hour = (now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
                sleep_s = max(0.0, (next_hour - now).total_seconds())
                await asyncio.sleep(sleep_s)

                # Recalcule à l'éveil (pour précision et DST)
                ts = int(next_hour.timestamp())
                event_id = f"hourly:{next_hour.strftime('%Y%m%d%H')}"   # idempotence forte
                title = f"Événement horaire — {next_hour.strftime('%H:%M')}"
                payload = {"desc": "Tick horaire LaRue.exe (DEV/PROD selon env)."}

                ev = repo_events.upsert_event(
                    event_id=event_id,
                    kind="hourly_tick",
                    title=title,
                    starts_at=ts,
                    ends_at=0,            # ou ts+3600 si tu veux une fenêtre d'1h
                    payload=payload,
                    status="scheduled",
                )
                log.info("HourlyPlanner: event prêt %s à %s", ev["id"], next_hour.isoformat())

                # Petite pause pour éviter un double seed si la boucle repart très vite
                await asyncio.sleep(1)

            except Exception:
                log.exception("HourlyPlanner: erreur boucle")
                await asyncio.sleep(10)
