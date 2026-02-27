from __future__ import annotations

from typing import Any, Optional


class AudioSource:
    def read(self) -> bytes:
        raise NotImplementedError

    def is_opus(self) -> bool:
        return False


class PCMVolumeTransformer(AudioSource):
    def __init__(self, original: AudioSource, *, volume: float = 1.0) -> None:
        self.original = original
        self.volume = volume

    def read(self) -> bytes:
        return self.original.read()


class VoiceClient:
    def __init__(self, client: Any, channel: Any, *, timeout: float = 60.0) -> None:
        self._client = client
        self.channel = channel
        self.timeout = timeout
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self, *, timeout: Optional[float] = None) -> None:
        self._connected = False
        raise NotImplementedError("Fluxer voice transport is not implemented")

    async def disconnect(self, *, force: bool = False) -> None:
        self._connected = False

    def play(self, source: AudioSource) -> None:
        raise NotImplementedError("Audio playback is not implemented")

    def stop(self) -> None:
        return None

