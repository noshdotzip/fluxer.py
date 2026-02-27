import asyncio
import json
from typing import Any, Dict, Optional

import aiohttp

from .errors import GatewayError


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

        self._ws = await self._client.http.session.ws_connect(url)
        self._listener_task = asyncio.create_task(self._listen())
        try:
            await self._ready.wait()
        except asyncio.CancelledError:
            await self.close()
            raise

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
            elif msg.type == aiohttp.WSMsgType.ERROR:
                raise GatewayError("Gateway websocket error")

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
            await self._identify()
        elif op == 11:  # HEARTBEAT_ACK
            return
        elif op == 0:  # DISPATCH
            if event == "READY":
                self._session_id = data.get("session_id")
                self._client._set_user(data.get("user"))
                if not self._ready.is_set():
                    self._ready.set()
                await self._client._dispatch_gateway_event(event, data)
                return
            await self._client._dispatch_gateway_event(event, data)
        elif op == 7:  # RECONNECT
            await self._reconnect()
        elif op == 9:  # INVALID_SESSION
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
