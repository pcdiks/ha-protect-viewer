"""HTTP server behind HA Ingress: UI, camera API and go2rtc websocket proxy."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import aiohttp
from aiohttp import web

from . import go2rtc
from .protect import Camera, ProtectClient, ProtectError

_LOGGER = logging.getLogger(__name__)

WWW = Path(__file__).parent / "www"
SNAPSHOT_TTL = 10  # seconds
# Ingress proxies all requests from this address; local addresses are for development.
ALLOWED_REMOTES = {"172.30.32.2", "127.0.0.1", "::1"}
GO2RTC_FILES = {"video-stream.js", "video-rtc.js"}


@dataclass
class State:
    grid_quality: str
    show_stream_type: bool = False
    cameras: list[Camera] = field(default_factory=list)
    error: str | None = None
    snapshots: dict[str, tuple[float, bytes]] = field(default_factory=dict)

    def streams(self) -> set[str]:
        names = set()
        for camera in self.cameras:
            names.update(go2rtc.camera_streams(camera, self.grid_quality).values())
        return names


@web.middleware
async def ingress_only(request: web.Request, handler):
    if request.remote not in ALLOWED_REMOTES:
        raise web.HTTPForbidden()
    return await handler(request)


async def index(request: web.Request) -> web.FileResponse:
    return web.FileResponse(WWW / "index.html", headers={"Cache-Control": "no-cache"})


async def cameras(request: web.Request) -> web.Response:
    state: State = request.app["state"]
    result = []
    for camera in state.cameras:
        streams = go2rtc.camera_streams(camera, state.grid_quality)
        result.append(
            {
                "id": camera.id,
                "name": camera.name,
                "model": camera.model,
                "connected": camera.connected,
                "streams": streams or None,
            }
        )
    return web.json_response(
        {
            "error": state.error,
            "show_stream_type": state.show_stream_type,
            "cameras": result,
        }
    )


async def snapshot(request: web.Request) -> web.Response:
    state: State = request.app["state"]
    camera_id = request.match_info["camera_id"]
    if camera_id not in {camera.id for camera in state.cameras}:
        raise web.HTTPNotFound()
    cached = state.snapshots.get(camera_id)
    if cached and time.monotonic() - cached[0] < SNAPSHOT_TTL:
        image = cached[1]
    else:
        protect: ProtectClient = request.app["protect"]
        try:
            image = await protect.snapshot(camera_id, width=640)
        except ProtectError as err:
            _LOGGER.debug("Snapshot for %s failed: %s", camera_id, err)
            raise web.HTTPBadGateway() from err
        state.snapshots[camera_id] = (time.monotonic(), image)
    return web.Response(
        body=image, content_type="image/jpeg", headers={"Cache-Control": "no-store"}
    )


async def go2rtc_file(request: web.Request) -> web.Response:
    """Serve the go2rtc web player scripts from the bundled go2rtc."""
    name = request.match_info["name"]
    if name not in GO2RTC_FILES:
        raise web.HTTPNotFound()
    http: aiohttp.ClientSession = request.app["http"]
    try:
        async with http.get(f"{go2rtc.API_URL}/{name}") as resp:
            if resp.status != 200:
                raise web.HTTPBadGateway()
            body = await resp.read()
    except aiohttp.ClientError as err:
        raise web.HTTPBadGateway() from err
    return web.Response(
        body=body,
        content_type="application/javascript",
        headers={"Cache-Control": "max-age=3600"},
    )


async def stream_ws(request: web.Request) -> web.WebSocketResponse:
    """Relay the player websocket to go2rtc, limited to known streams."""
    state: State = request.app["state"]
    src = request.query.get("src", "")
    if src not in state.streams():
        raise web.HTTPNotFound()

    client = web.WebSocketResponse(max_msg_size=0)
    await client.prepare(request)
    http: aiohttp.ClientSession = request.app["http"]
    try:
        async with http.ws_connect(
            f"{go2rtc.API_URL}/api/ws", params={"src": src}, max_msg_size=0
        ) as upstream:
            relays = [
                asyncio.create_task(_relay(client, upstream)),
                asyncio.create_task(_relay(upstream, client)),
            ]
            _, pending = await asyncio.wait(relays, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
    except aiohttp.ClientError as err:
        _LOGGER.warning("Cannot connect to go2rtc for %s: %s", src, err)
    await client.close()
    return client


async def _relay(source, target) -> None:
    async for msg in source:
        if msg.type == aiohttp.WSMsgType.TEXT:
            await target.send_str(msg.data)
        elif msg.type == aiohttp.WSMsgType.BINARY:
            await target.send_bytes(msg.data)
        else:
            break


def create_app(state: State, protect: ProtectClient) -> web.Application:
    app = web.Application(middlewares=[ingress_only])
    app["state"] = state
    app["protect"] = protect
    app.router.add_get("/", index)
    app.router.add_get("/api/cameras", cameras)
    app.router.add_get("/api/cameras/{camera_id}/snapshot", snapshot)
    app.router.add_get("/api/ws", stream_ws)
    app.router.add_get("/go2rtc/{name}", go2rtc_file)
    app.router.add_static("/static", WWW)

    async def http_session(app: web.Application):
        app["http"] = aiohttp.ClientSession()
        yield
        await app["http"].close()

    app.cleanup_ctx.append(http_session)
    return app
