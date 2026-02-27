import asyncio
import json
import logging
import zlib
from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse
from typing import Any, Dict, Optional

import aiohttp

from .errors import GatewayError


LOGGER = logging.getLogger("fluxer")


class Gateway:
    def __init__(self, client, *, heartbeat_timeout: float = 30.0) -> None:
        self._client = client
        self._heartbeat_timeout = heartbeat_timeout
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._listener_task: Optional[asyncio.Task] = None
        self._sequence: Optional[int] = None
        self._session_id: Optional[str] = None
        self._ready = asyncio.Event()

    async def connect(self) -> None:
        gateway_info = await self._client.http.get_gateway_bot()
        url = gateway_info.get("url")
        if not url:
            raise GatewayError("Gateway URL missing from /gateway/bot response")

        url = self._normalize_gateway_url(url)
        LOGGER.info("Connecting to gateway %s", url)
        self._ws = await self._client.http.session.ws_connect(url)
        self._listener_task = asyncio.create_task(self._listen())
        ready_task = asyncio.create_task(self._ready.wait())
        try:
            done, pending = await asyncio.wait(
                [ready_task, self._listener_task],
                timeout=self._heartbeat_timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if ready_task in done and self._ready.is_set():
                return
            if self._listener_task in done:
                exc = self._listener_task.exception()
                raise GatewayError("Gateway closed before READY") from exc
            raise GatewayError("Timed out waiting for READY")
        except asyncio.CancelledError:
            await self.close()
            raise
        finally:
            if not ready_task.done():
                ready_task.cancel()

    async def close(self) -> None:
        if self._listener_task:
            self._listener_task.cancel()
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._ws:
            await self._ws.close()

    async def _identify(self) -> None:
        payload = {
            "op": 2,
            "d": {
                "token": self._client.token,
                "intents": int(self._client.intents),
                "properties": {
                    "os": self._client._os,
                    "browser": "fluxer.py",
                    "device": "fluxer.py",
                },
            },
        }
        LOGGER.info("Identifying with gateway")
        await self._send(payload)

    async def _heartbeat_loop(self, interval_ms: int) -> None:
        try:
            while True:
                await asyncio.sleep(interval_ms / 1000)
                await self._send({"op": 1, "d": self._sequence})
        except asyncio.CancelledError:
            return

    async def _listen(self) -> None:
        assert self._ws is not None
        async for msg in self._ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                payload = json.loads(msg.data)
                await self._handle_payload(payload)
            elif msg.type == aiohttp.WSMsgType.BINARY:
                data = msg.data
                try:
                    text = data.decode("utf-8")
                except UnicodeDecodeError:
                    try:
                        text = zlib.decompress(data).decode("utf-8")
                    except Exception as exc:
                        raise GatewayError("Gateway binary payload decode failed") from exc
                payload = json.loads(text)
                await self._handle_payload(payload)
            elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED):
                code = self._ws.close_code if self._ws else None
                raise GatewayError(f"Gateway websocket closed (code={code})")
            elif msg.type == aiohttp.WSMsgType.ERROR:
                raise GatewayError("Gateway websocket error")

        if self._ws and self._ws.closed:
            code = self._ws.close_code
            raise GatewayError(f"Gateway websocket closed (code={code})")

    async def _handle_payload(self, payload: Dict[str, Any]) -> None:
        op = payload.get("op")
        data = payload.get("d")
        event = payload.get("t")
        seq = payload.get("s")

        if seq is not None:
            self._sequence = seq

        if op == 10:  # HELLO
            interval_ms = int(data.get("heartbeat_interval", 45000))
            if self._heartbeat_task:
                self._heartbeat_task.cancel()
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(interval_ms))
            LOGGER.info("Gateway HELLO (heartbeat=%sms)", interval_ms)
            await self._identify()
        elif op == 11:  # HEARTBEAT_ACK
            return
        elif op == 0:  # DISPATCH
            if event == "READY":
                self._session_id = data.get("session_id")
                self._client._set_user(data.get("user"))
                LOGGER.info("Gateway READY (session_id=%s)", self._session_id)
                if not self._ready.is_set():
                    self._ready.set()
                await self._client._dispatch_gateway_event(event, data)
                return
            await self._client._dispatch_gateway_event(event, data)
        elif op == 7:  # RECONNECT
            LOGGER.info("Gateway requested reconnect")
            await self._reconnect()
        elif op == 9:  # INVALID_SESSION
            LOGGER.warning("Gateway invalid session; re-identifying")
            await asyncio.sleep(5)
            await self._identify()

    async def _reconnect(self) -> None:
        await self.close()
        await self.connect()

    async def send(self, payload: Dict[str, Any]) -> None:
        await self._send(payload)

    async def _send(self, payload: Dict[str, Any]) -> None:
        assert self._ws is not None
        await self._ws.send_str(json.dumps(payload))

    @staticmethod
    def _normalize_gateway_url(url: str) -> str:
        parsed = urlparse(url)
        query = dict(parse_qsl(parsed.query))
        if "encoding" not in query:
            query["encoding"] = "json"
        if "v" not in query:
            query["v"] = "1"
        new_query = urlencode(query)
        return urlunparse(parsed._replace(query=new_query))
