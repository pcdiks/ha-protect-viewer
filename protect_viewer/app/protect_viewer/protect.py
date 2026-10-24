"""Minimal client for the UniFi Protect API on a UniFi OS console."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

import aiohttp

_LOGGER = logging.getLogger(__name__)

# Protect channel id -> quality name
CHANNEL_QUALITY = {0: "high", 1: "medium", 2: "low"}


class ProtectError(Exception):
    """Raised when the console rejects a request or cannot be reached."""


@dataclass
class Camera:
    id: str
    name: str
    model: str
    connected: bool
    # quality -> RTSP alias, only for channels with RTSP enabled
    rtsp: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_bootstrap(cls, data: dict) -> Camera:
        rtsp = {}
        for channel in data.get("channels", []):
            quality = CHANNEL_QUALITY.get(channel.get("id"))
            if quality and channel.get("isRtspEnabled") and channel.get("rtspAlias"):
                rtsp[quality] = channel["rtspAlias"]
        return cls(
            id=data["id"],
            name=data.get("name") or data.get("displayName") or data["id"],
            model=data.get("marketName") or data.get("type", ""),
            connected=data.get("state") == "CONNECTED",
            rtsp=rtsp,
        )


class ProtectClient:
    def __init__(self, host: str, username: str, password: str, verify_ssl: bool) -> None:
        self.host = host
        self._base = f"https://{host}"
        self._username = username
        self._password = password
        self._verify_ssl = verify_ssl
        self._session: aiohttp.ClientSession | None = None
        self._login_lock = asyncio.Lock()
        self._logged_in = False

    async def start(self) -> None:
        # unsafe=True: the console is usually addressed by IP, and aiohttp
        # ignores cookies for IP hosts otherwise.
        self._session = aiohttp.ClientSession(
            cookie_jar=aiohttp.CookieJar(unsafe=True),
            connector=aiohttp.TCPConnector(ssl=None if self._verify_ssl else False),
            timeout=aiohttp.ClientTimeout(total=30),
        )

    async def close(self) -> None:
        if self._session:
            await self._session.close()

    async def _login(self) -> None:
        async with self._login_lock:
            assert self._session
            try:
                async with self._session.post(
                    f"{self._base}/api/auth/login",
                    json={
                        "username": self._username,
                        "password": self._password,
                        "rememberMe": True,
                        "token": "",
                    },
                ) as resp:
                    if resp.status in (401, 403):
                        raise ProtectError("Login refused: check username and password")
                    if resp.status != 200:
                        raise ProtectError(f"Login failed: HTTP {resp.status}")
            except aiohttp.ClientError as err:
                raise ProtectError(f"Cannot reach {self.host}: {err}") from err
            self._logged_in = True
            _LOGGER.info("Logged in to UniFi console %s", self.host)

    async def request(self, path: str, **kwargs) -> aiohttp.ClientResponse:
        """GET a Protect API path; the caller must release the response."""
        assert self._session
        if not self._logged_in:
            await self._login()
        for attempt in range(2):
            try:
                resp = await self._session.get(
                    f"{self._base}/proxy/protect/api{path}", **kwargs
                )
            except aiohttp.ClientError as err:
                raise ProtectError(f"Cannot reach {self.host}: {err}") from err
            if resp.status == 401 and attempt == 0:
                resp.release()
                self._logged_in = False
                await self._login()
                continue
            if resp.status >= 400:
                resp.release()
                raise ProtectError(f"GET {path} failed: HTTP {resp.status}")
            return resp
        raise ProtectError(f"GET {path} failed: not authorized")

    async def cameras(self) -> list[Camera]:
        resp = await self.request("/bootstrap")
        async with resp:
            bootstrap = await resp.json()
        return [
            Camera.from_bootstrap(cam)
            for cam in bootstrap.get("cameras", [])
            if cam.get("isAdopted", True) and not cam.get("isAdoptedByOther", False)
        ]

    async def snapshot(self, camera_id: str, width: int) -> bytes:
        resp = await self.request(
            f"/cameras/{camera_id}/snapshot", params={"w": str(width), "force": "true"}
        )
        async with resp:
            return await resp.read()
