"""Entry point: load options, keep the camera list fresh, run go2rtc and the web server."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
from pathlib import Path

import aiohttp
from aiohttp import web

from . import go2rtc
from .protect import Camera, ProtectClient, ProtectError
from .server import State, create_app

_LOGGER = logging.getLogger("protect_viewer")

OPTIONS_PATH = Path(os.environ.get("PV_OPTIONS", "/data/options.json"))
GO2RTC_BINARY = os.environ.get("PV_GO2RTC", "/usr/local/bin/go2rtc")
GO2RTC_CONFIG = Path(os.environ.get("PV_GO2RTC_CONFIG", "/tmp/go2rtc.yaml"))
PORT = int(os.environ.get("PV_PORT", "8099"))
REFRESH_INTERVAL = 600  # seconds between camera list refreshes
RETRY_INTERVAL = 30  # seconds before retrying after an error


async def detect_webrtc_ip() -> str | None:
    """Ask the Supervisor for the primary IPv4 address of the HA host."""
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "http://supervisor/network/info",
                headers={"Authorization": f"Bearer {token}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = (await resp.json())["data"]
    except (aiohttp.ClientError, asyncio.TimeoutError, KeyError, ValueError) as err:
        _LOGGER.warning("Cannot detect host IP for WebRTC: %s", err)
        return None
    for interface in data.get("interfaces", []):
        addresses = (interface.get("ipv4") or {}).get("address") or []
        if interface.get("primary") and addresses:
            return addresses[0].split("/")[0]
    return None


def select_cameras(cameras: list[Camera], names: list[str]) -> list[Camera]:
    """Keep only the configured cameras, in configured order; all when empty."""
    if not names:
        return sorted(cameras, key=lambda camera: camera.name.lower())
    by_name = {camera.name.lower(): camera for camera in cameras}
    selected = []
    for name in names:
        camera = by_name.get(name.strip().lower())
        if camera:
            selected.append(camera)
        else:
            _LOGGER.warning("Camera %r not found in Protect", name)
    return selected


async def refresh_loop(options: dict, state: State, protect: ProtectClient, runner: go2rtc.Go2rtc, webrtc_ip: str | None) -> None:
    while True:
        try:
            cameras = select_cameras(await protect.cameras(), options.get("cameras") or [])
        except ProtectError as err:
            _LOGGER.error("%s", err)
            state.error = str(err)
            await asyncio.sleep(RETRY_INTERVAL)
            continue
        state.error = None
        state.cameras = cameras
        for camera in cameras:
            if not go2rtc.camera_streams(camera, state.grid_quality):
                _LOGGER.warning("No RTSP stream enabled for camera %r", camera.name)
        await runner.apply(
            go2rtc.build_config(cameras, protect.host, state.grid_quality, webrtc_ip)
        )
        await asyncio.sleep(REFRESH_INTERVAL)


async def main() -> None:
    options = json.loads(OPTIONS_PATH.read_text())
    logging.basicConfig(
        level=options.get("log_level", "info").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    webrtc_ip = options.get("webrtc_ip") or await detect_webrtc_ip()
    _LOGGER.info("WebRTC address: %s", webrtc_ip or "not set, using MSE only on the LAN")

    protect = ProtectClient(
        options["host"], options["username"], options["password"], options["verify_ssl"]
    )
    await protect.start()
    state = State(
        grid_quality=options["grid_quality"],
        show_stream_type=options.get("show_stream_type", False),
    )
    runner = go2rtc.Go2rtc(GO2RTC_BINARY, GO2RTC_CONFIG)

    access_log = logging.getLogger("aiohttp.access") if options.get("log_level") == "debug" else None
    web_runner = web.AppRunner(create_app(state, protect), access_log=access_log)
    await web_runner.setup()
    await web.TCPSite(web_runner, "0.0.0.0", PORT).start()
    _LOGGER.info("Listening on port %d", PORT)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    refresh = asyncio.create_task(refresh_loop(options, state, protect, runner, webrtc_ip))
    await stop.wait()

    refresh.cancel()
    await runner.stop()
    await web_runner.cleanup()
    await protect.close()


if __name__ == "__main__":
    asyncio.run(main())
