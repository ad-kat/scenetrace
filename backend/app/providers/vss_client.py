"""Authenticated HTTP client for the Team VSS retrieval API.

Verified contracts (retrieval/login, search, agent-qa, videos skills):
  POST /api/v1/auth/login
  POST /api/v1/search
  POST /api/v1/agent/ask
  POST /api/v1/agent/search-and-answer
  GET  /api/v1/tools/segments
  GET  /api/v1/videos/explore
  GET  /api/v1/videos/stream?source=&token=
  GET  /api/v1/videos/detections?source=
  GET  /api/v1/metadata/values?field=
"""
from __future__ import annotations

import logging
import threading
from typing import Any
from urllib.parse import quote

import httpx

from app.providers.base import ProviderNotConfigured

logger = logging.getLogger(__name__)


class VssClient:
    """JWT-caching client for the organizer VSS backend."""

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        timeout: float = 30.0,
    ) -> None:
        if not base_url or not username or not password:
            raise ProviderNotConfigured(
                "VSS_URL/INGRESS_URL, VSS_USERNAME/USERNAME, and "
                "VSS_PASSWORD/PASSWORD must be set for live mode."
            )
        self._base = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._timeout = timeout
        self._token: str | None = None
        self._lock = threading.Lock()
        self._client = httpx.AsyncClient(timeout=timeout, follow_redirects=True)

    @property
    def base_url(self) -> str:
        return self._base

    async def aclose(self) -> None:
        await self._client.aclose()

    async def login(self, force: bool = False) -> str:
        with self._lock:
            if self._token and not force:
                return self._token
        resp = await self._client.post(
            f"{self._base}/api/v1/auth/login",
            json={"username": self._username, "password": self._password},
        )
        if resp.status_code != 200:
            raise ProviderNotConfigured(
                f"VSS login failed with HTTP {resp.status_code}"
            )
        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise ProviderNotConfigured("VSS login response missing access_token")
        with self._lock:
            self._token = token
        return token

    async def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        auth: bool = True,
    ) -> Any:
        headers: dict[str, str] = {}
        if auth:
            token = await self.login()
            headers["Authorization"] = f"Bearer {token}"

        url = f"{self._base}{path}"
        resp = await self._client.request(
            method, url, json=json_body, params=params, headers=headers
        )
        if resp.status_code == 401 and auth:
            token = await self.login(force=True)
            headers["Authorization"] = f"Bearer {token}"
            resp = await self._client.request(
                method, url, json=json_body, params=params, headers=headers
            )
        resp.raise_for_status()
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    async def search(self, body: dict[str, Any]) -> dict[str, Any]:
        return await self.request("POST", "/api/v1/search", json_body=body)

    async def agent_ask(self, body: dict[str, Any]) -> dict[str, Any]:
        return await self.request("POST", "/api/v1/agent/ask", json_body=body)

    async def search_and_answer(self, body: dict[str, Any]) -> dict[str, Any]:
        return await self.request(
            "POST", "/api/v1/agent/search-and-answer", json_body=body
        )

    async def explore(
        self, *, limit: int = 48, offset: int = 0, location: str | None = None
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"scope": "all", "limit": limit, "offset": offset}
        if location:
            params["location"] = location
        return await self.request("GET", "/api/v1/videos/explore", params=params)

    async def segments(self, original_video: str) -> dict[str, Any]:
        return await self.request(
            "GET",
            "/api/v1/tools/segments",
            params={"original_video": original_video},
        )

    async def detections(self, source: str) -> dict[str, Any]:
        return await self.request(
            "GET",
            "/api/v1/videos/detections",
            params={"source": source},
        )

    async def metadata_values(self, field: str, *, limit: int = 50) -> dict[str, Any]:
        return await self.request(
            "GET",
            "/api/v1/metadata/values",
            params={"field": field, "limit": limit},
        )

    async def metadata_schema(self) -> dict[str, Any]:
        return await self.request("GET", "/api/v1/metadata/schema")

    def stream_url(self, source: str, token: str) -> str:
        return (
            f"{self._base}/api/v1/videos/stream"
            f"?source={quote(source, safe='')}&token={quote(token, safe='')}"
        )

    async def stream_proxy_request(
        self,
        source: str,
        *,
        range_header: str | None = None,
    ) -> httpx.Response:
        token = await self.login()
        url = self.stream_url(source, token)
        headers = {}
        if range_header:
            headers["Range"] = range_header
        # Caller must read/close the response.
        return await self._client.send(
            self._client.build_request("GET", url, headers=headers),
            stream=True,
        )
