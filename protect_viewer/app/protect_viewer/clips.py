"""Exports detection clips from Protect and keeps recent ones on disk."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from .protect import ProtectClient

_LOGGER = logging.getLogger(__name__)

PADDING = 2000  # ms of video before and after a detection
MAX_LENGTH = 10 * 60 * 1000  # ms, longer detections are cut off
CHANNELS = {"high": 0, "low": 2}


class ClipCache:
    def __init__(self, protect: ProtectClient, directory: Path, max_bytes: int, quality: str) -> None:
        self._protect = protect
        self._dir = directory
        self._max_bytes = max_bytes
        self._channel = CHANNELS[quality]
        self._locks: dict[str, asyncio.Lock] = {}
        self._dir.mkdir(parents=True, exist_ok=True)
        # Clips from a previous run may be from a different quality setting
        for old in self._dir.iterdir():
            old.unlink()

    async def get(self, event: dict) -> Path:
        """Return the path of the clip for an event, exporting it when needed."""
        path = self._dir / f"{event['id']}.mp4"
        finished = event.get("end") is not None
        lock = self._locks.setdefault(event["id"], asyncio.Lock())
        async with lock:
            # A detection that is still going on gets a fresh export every time
            if finished and path.exists():
                path.touch()
                return path
            start = event["start"] - PADDING
            end = (event["end"] or int(time.time() * 1000)) + PADDING
            end = min(end, start + MAX_LENGTH)
            partial = path.with_suffix(".part")
            try:
                await self._protect.export(event["camera"], start, end, self._channel, partial)
            except BaseException:
                partial.unlink(missing_ok=True)
                raise
            partial.replace(path)
        self._locks.pop(event["id"], None)
        self._evict(keep=path)
        return path

    def _evict(self, keep: Path) -> None:
        clips = sorted(
            (clip for clip in self._dir.glob("*.mp4") if clip != keep),
            key=lambda clip: clip.stat().st_mtime,
        )
        clips.append(keep)  # counted, but never removed while it's about to be served
        total = sum(clip.stat().st_size for clip in clips)
        while len(clips) > 1 and total > self._max_bytes:
            oldest = clips.pop(0)
            total -= oldest.stat().st_size
            oldest.unlink()
            _LOGGER.debug("Removed %s from the clip cache", oldest.name)
