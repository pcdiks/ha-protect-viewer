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
        # Session cookie and CSRF token from the login, sent with every request
        # the same way the UniFi web app does.
        self._token: str | None = None
        self._csrf: str | None = None

    async def start(self) -> None:
        self._session = aiohttp.ClientSession(
            cookie_jar=aiohttp.DummyCookieJar(),
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
                    cookie = resp.cookies.get("TOKEN")
                    self._token = cookie.value if cookie else None
                    self._csrf = resp.headers.get("X-Csrf-Token")
            except aiohttp.ClientError as err:
                raise ProtectError(f"Cannot reach {self.host}: {err}") from err
            if not self._token:
                raise ProtectError("Login succeeded but the console sent no session cookie")
            _LOGGER.info("Logged in to UniFi console %s", self.host)
            _LOGGER.debug("CSRF token received: %s", bool(self._csrf))

    def _headers(self) -> dict[str, str]:
        headers = {"Cookie": f"TOKEN={self._token}"}
        if self._csrf:
            headers["X-Csrf-Token"] = self._csrf
        return headers

    async def request(self, path: str, **kwargs) -> aiohttp.ClientResponse:
        """GET a Protect API path; the caller must release the response."""
        assert self._session
        if not self._token:
            await self._login()
        for attempt in range(2):
            try:
                resp = await self._session.get(
                    f"{self._base}/proxy/protect/api{path}",
                    headers=self._headers(),
                    **kwargs,
                )
            except aiohttp.ClientError as err:
                raise ProtectError(f"Cannot reach {self.host}: {err}") from err
            # The console rotates the CSRF token now and then
            self._csrf = resp.headers.get("X-Updated-Csrf-Token", self._csrf)
            if resp.status == 401 and attempt == 0:
                resp.release()
                self._token = None
                await self._login()
                continue
            if resp.status >= 400:
                body = (await resp.text())[:300]
                resp.release()
                if resp.status in (401, 403):
                    raise ProtectError(
                        f"Protect refused access ({resp.status}). Check that the user "
                        f"has a Protect role. Console said: {body}"
                    )
                raise ProtectError(f"GET {path} failed: HTTP {resp.status}: {body}")
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
