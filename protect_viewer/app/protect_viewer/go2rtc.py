"""Generates the go2rtc config from Protect cameras and supervises the process."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from .protect import Camera

_LOGGER = logging.getLogger(__name__)

API_LISTEN = "127.0.0.1:1984"
API_URL = f"http://{API_LISTEN}"
WEBRTC_PORT = 8555

# Fallback order when the preferred quality has no RTSP stream enabled
FALLBACK = {
    "high": ["high", "medium", "low"],
    "medium": ["medium", "low", "high"],
    "low": ["low", "medium", "high"],
}


def pick_alias(camera: Camera, quality: str) -> str | None:
    for candidate in FALLBACK[quality]:
        if candidate in camera.rtsp:
            return camera.rtsp[candidate]
    return None


def camera_streams(camera: Camera, grid_quality: str) -> dict[str, str]:
    """Return {"main": stream name, "grid": stream name} for a camera, or {}."""
    main = pick_alias(camera, "high")
    if not main:
        return {}
    grid = pick_alias(camera, grid_quality)
    return {"main": camera.id, "grid": camera.id if grid == main else f"{camera.id}_grid"}


def build_config(
    cameras: list[Camera], host: str, grid_quality: str, webrtc_ip: str | None
) -> dict:
    streams = {}
    for camera in cameras:
        names = camera_streams(camera, grid_quality)
        if not names:
            continue
        # rtspx = RTSPS without certificate verification (Protect uses self-signed)
        streams[names["main"]] = f"rtspx://{host}:7441/{pick_alias(camera, 'high')}"
        if names["grid"] != names["main"]:
            streams[names["grid"]] = f"rtspx://{host}:7441/{pick_alias(camera, grid_quality)}"

    candidates = [f"{webrtc_ip}:{WEBRTC_PORT}"] if webrtc_ip else []
    candidates.append(f"stun:{WEBRTC_PORT}")
    return {
        "api": {"listen": API_LISTEN},
        "rtsp": {"listen": ""},
        "webrtc": {"listen": f":{WEBRTC_PORT}", "candidates": candidates},
        "log": {"level": "info"},
        "streams": streams,
    }


class Go2rtc:
    def __init__(self, binary: str, config_path: Path) -> None:
        self._binary = binary
        self._config_path = config_path
        self._config: dict | None = None
        self._proc: asyncio.subprocess.Process | None = None
        self._task: asyncio.Task | None = None
        self._stopping = False

    async def apply(self, config: dict) -> None:
        """Write the config and (re)start go2rtc when it changed."""
        if config == self._config:
            return
        self._config = config
        # go2rtc reads YAML, and JSON is valid YAML
        self._config_path.write_text(json.dumps(config, indent=2))
        _LOGGER.info("go2rtc config updated with %d streams", len(config["streams"]))
        if self._task is None:
            self._task = asyncio.create_task(self._supervise())
        elif self._proc and self._proc.returncode is None:
            self._proc.terminate()  # _supervise restarts it with the new config

    async def _supervise(self) -> None:
        while not self._stopping:
            self._proc = await asyncio.create_subprocess_exec(
                self._binary, "-config", str(self._config_path)
            )
            code = await self._proc.wait()
            if self._stopping:
                return
            _LOGGER.info("go2rtc exited with code %s, restarting", code)
            await asyncio.sleep(2)

    async def stop(self) -> None:
        self._stopping = True
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
            await self._proc.wait()
        if self._task:
            await self._task
